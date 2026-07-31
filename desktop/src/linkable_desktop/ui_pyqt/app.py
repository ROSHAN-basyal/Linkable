from __future__ import annotations

import argparse
import hashlib
import signal
import subprocess
import sys
import time
from pathlib import Path
from threading import Event

from linkable_desktop.app.runtime import BlockingPromptBridge, DesktopRuntime
from linkable_desktop.config import CONFIG_DIR
from linkable_desktop.proto import calls_pb2, notifications_pb2
from linkable_desktop.ui_qt.call_notifications import CallNotificationController
from linkable_desktop.ui_qt.native_notifications import NativeNotificationAction, NativeNotificationManager, copy_text_to_desktop_clipboard


ROOT_DIR = Path(__file__).resolve().parents[4]


def main(argv: list[str] | None = None) -> int:
    """Run the Linkable PyQt6 desktop application."""

    parser = argparse.ArgumentParser(description="Linkable desktop app")
    parser.add_argument("--background-service", action="store_true", help="Run LAN discovery without showing the UI")
    args = parser.parse_args(argv)
    if args.background_service:
        return _run_background_service()
    return _run_gui()


def _run_gui() -> int:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication

    from linkable_desktop.app.setup_state import load_first_run_state
    from linkable_desktop.config import load_discovery_config
    from linkable_desktop.ui_pyqt.first_run_wizard import FirstRunWizard
    from linkable_desktop.ui_pyqt.main_window import MainWindow
    from linkable_desktop.ui_pyqt.runtime_bridge import RuntimeBridge
    from linkable_desktop.ui_pyqt.theme import build_stylesheet

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Linkable")
    app.setStyleSheet(build_stylesheet())
    background_service_paused = _pause_background_service_for_gui()

    port = load_discovery_config().service_port
    if not _show_compatibility_gate(port):
        if background_service_paused:
            _resume_background_service_after_gui()
        return 2

    if not load_first_run_state().completed:
        wizard = FirstRunWizard(ROOT_DIR)
        wizard.exec()

    bridge = RuntimeBridge()
    runtime = DesktopRuntime(
        root_dir=ROOT_DIR,
        on_log=bridge.log_received.emit,
        on_devices_changed=bridge.devices_changed.emit,
        on_notifications_changed=bridge.notifications_changed.emit,
        on_clipboard_changed=bridge.clipboard_changed.emit,
        on_shared_apps_changed=bridge.shared_apps_changed.emit,
        on_phone_files_changed=bridge.phone_files_changed.emit,
        on_contacts_changed=bridge.contacts_changed.emit,
        # The server has already verified that the user opened the short-lived
        # pairing window. The six-digit challenge remains the authentication
        # step, so a second allow/deny dialog only adds friction.
        confirm_pairing=_allow_pairing_inside_user_window,
        prompt_code=bridge.prompt_code,
    )
    window = MainWindow(runtime, bridge, ROOT_DIR)
    app.aboutToQuit.connect(_resume_background_service_after_gui)
    window.show()
    return app.exec()


def _allow_pairing_inside_user_window(phone_name: str, device_id: str, address: str) -> bool:
    """Allow the code challenge after PairingServer validates the user-opened gate."""

    return True


def _show_compatibility_gate(port: int) -> bool:
    from linkable_desktop.app.compatibility import run_compatibility_checks
    from linkable_desktop.app.setup_state import load_first_run_state, save_skipped_optional_checks
    from linkable_desktop.ui_pyqt.compatibility_gate import CompatibilityGate
    from linkable_desktop.ui_pyqt.theme import build_stylesheet

    while True:
        report = run_compatibility_checks(port)
        if report.all_passed:
            return True
        skipped = set(load_first_run_state().skipped_optional_checks)
        if not report.failed_critical_checks and all(
            check.check_id in skipped for check in report.failed_noncritical_checks
        ):
            return True
        dialog = CompatibilityGate(report)
        dialog.setStyleSheet(build_stylesheet())
        dialog.recheck_requested.connect(lambda: dialog.done(2))
        result = dialog.exec()
        if result == 2:
            continue
        if result == CompatibilityGate.DialogCode.Accepted and dialog.skip_noncritical:
            save_skipped_optional_checks(tuple(check.check_id for check in report.failed_noncritical_checks))
        return result == CompatibilityGate.DialogCode.Accepted


def _run_background_service() -> int:
    prompt_bridge = BlockingPromptBridge()
    notification_fingerprints: dict[str, str] = {}
    active_ringing_call_ids: set[str] = set()
    desktop_answered_call_ids: set[str] = set()
    ongoing_call_ids: set[str] = set()
    clipboard_update_ids: set[str] = set()
    runtime_ref: dict[str, DesktopRuntime] = {}

    def native_action(notification_id: str, action: NativeNotificationAction) -> None:
        runtime = runtime_ref.get("runtime")
        if runtime is None:
            return
        if action.kind == "clipboard_copy":
            copy_text_to_desktop_clipboard(action.payload)
            return
        if action.kind == "answer":
            desktop_answered_call_ids.add(notification_id)
        if action.kind in {"hangup", "decline"}:
            native_notifications.close(notification_id)
        if action.kind == "reply":
            print(f"[native notification] Reply requires the GUI for text input: {notification_id}")
            return
        runtime.queue_notification_action(notification_id, action.action_id)

    native_notifications = NativeNotificationManager(
        icon_dir=CONFIG_DIR / "notification-icons",
        action_callback=native_action,
        call_answer_allowed=lambda: runtime_ref.get("runtime").active_phone_bluetooth_connected()
        if runtime_ref.get("runtime") is not None
        else False,
    )
    call_notifications = CallNotificationController(
        action_callback=lambda action: _handle_background_call_action(action, runtime_ref.get("runtime")),
        bluetooth_connected=lambda: runtime_ref.get("runtime").active_phone_bluetooth_connected()
        if runtime_ref.get("runtime") is not None
        else False,
    )

    def notifications_changed() -> None:
        runtime = runtime_ref.get("runtime")
        if runtime is None:
            return
        notifications = runtime.notifications()
        current_ids = {notification.notification_id for notification in notifications}
        tracked_call_ids = active_ringing_call_ids | ongoing_call_ids
        for notification_id in list(tracked_call_ids):
            if notification_id not in current_ids:
                native_notifications.close(notification_id)
                active_ringing_call_ids.discard(notification_id)
                desktop_answered_call_ids.discard(notification_id)
                ongoing_call_ids.discard(notification_id)
                notification_fingerprints.pop(notification_id, None)
        for notification in notifications:
            if _notification_is_active_call(notification):
                if _notification_is_ringing_call(notification):
                    if notification.notification_id not in active_ringing_call_ids:
                        active_ringing_call_ids.add(notification.notification_id)
                        native_notifications.show(notification)
                    continue
                if notification.notification_id in active_ringing_call_ids:
                    native_notifications.close(notification.notification_id)
                    active_ringing_call_ids.discard(notification.notification_id)
                    notification_fingerprints.pop(notification.notification_id, None)
                if (
                    notification.notification_id in desktop_answered_call_ids
                    and _notification_is_ongoing_call(notification)
                    and notification.notification_id not in ongoing_call_ids
                ):
                    ongoing_call_ids.add(notification.notification_id)
                    native_notifications.show(notification)
                    continue
                if not _notification_is_missed_call(notification):
                    continue
            fingerprint = _native_notification_fingerprint(notification)
            previous_fingerprint = notification_fingerprints.get(notification.notification_id)
            if previous_fingerprint == fingerprint:
                continue
            if previous_fingerprint is not None:
                native_notifications.close(notification.notification_id)
            notification_fingerprints[notification.notification_id] = fingerprint
            native_notifications.show(notification, silent=not _notification_is_fresh_for_popup(notification))

    def clipboard_changed() -> None:
        runtime = runtime_ref.get("runtime")
        if runtime is None:
            return
        for update in runtime.clipboard_updates():
            update_id = update.update_id or hashlib.sha256(update.text.encode()).hexdigest()
            if update_id in clipboard_update_ids:
                continue
            clipboard_update_ids.add(update_id)
            native_notifications.show_clipboard(update)

    def log(message: str) -> None:
        print(message)
        call_notifications.handle_call_metadata_log(message)

    runtime = DesktopRuntime(
        root_dir=ROOT_DIR,
        on_log=log,
        on_devices_changed=lambda: None,
        on_notifications_changed=notifications_changed,
        on_clipboard_changed=clipboard_changed,
        on_shared_apps_changed=lambda: None,
        on_phone_files_changed=lambda: None,
        on_contacts_changed=lambda: None,
        confirm_pairing=prompt_bridge.confirm_pairing,
        prompt_code=prompt_bridge.prompt_code,
    )
    runtime_ref["runtime"] = runtime
    stop_event = Event()

    def handle_stop(signum: int, frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    runtime.start()
    try:
        stop_event.wait()
    finally:
        runtime.stop()
    return 0


def _pause_background_service_for_gui() -> bool:
    """Stop the login background service while the interactive GUI owns the LAN port."""

    if not _systemctl_user_available():
        return False
    active = subprocess.run(
        ("systemctl", "--user", "is-active", "--quiet", "linkable-desktop.service"),
        capture_output=True,
        timeout=3,
        check=False,
    )
    if active.returncode != 0:
        return False
    stopped = subprocess.run(
        ("systemctl", "--user", "stop", "linkable-desktop.service"),
        capture_output=True,
        timeout=8,
        check=False,
    )
    return stopped.returncode == 0


def _resume_background_service_after_gui() -> None:
    """Restart the background service after the GUI closes."""

    if not _systemctl_user_available():
        return
    enabled = subprocess.run(
        ("systemctl", "--user", "is-enabled", "--quiet", "linkable-desktop.service"),
        capture_output=True,
        timeout=3,
        check=False,
    )
    if enabled.returncode != 0:
        return
    subprocess.run(
        ("systemctl", "--user", "start", "linkable-desktop.service"),
        capture_output=True,
        timeout=8,
        check=False,
    )


def _systemctl_user_available() -> bool:
    try:
        result = subprocess.run(
            ("systemctl", "--user", "status"),
            capture_output=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode in {0, 3}


def _handle_background_call_action(action: str, runtime: DesktopRuntime | None) -> None:
    if runtime is None:
        return
    if action == "answer":
        runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_ACCEPT)
    elif action == "decline":
        runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_REJECT)
    elif action == "hangup":
        runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_HANGUP)


def _native_notification_fingerprint(notification: object) -> str:
    serializer = getattr(notification, "SerializeToString", None)
    if callable(serializer):
        return hashlib.sha256(serializer()).hexdigest()
    return hashlib.sha256(repr(notification).encode("utf-8", errors="replace")).hexdigest()


def _notification_is_fresh_for_popup(notification: object) -> bool:
    posted = getattr(getattr(notification, "posted_at", None), "unix_epoch_ms", 0)
    if not posted:
        return True
    return int(time.time() * 1000) - int(posted) <= 60_000


def _notification_is_active_call(notification: object) -> bool:
    return bool(getattr(notification, "call_like", False)) and not _notification_is_missed_call(notification)


def _notification_is_ringing_call(notification: object) -> bool:
    if not getattr(notification, "call_like", False):
        return False
    state = str(getattr(notification, "call_state_hint", "")).lower()
    if state in {"incoming", "ringing"}:
        return True
    actions = getattr(notification, "actions", [])
    return any(
        getattr(action, "semantic", 0) == notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL
        for action in actions
    )


def _notification_is_ongoing_call(notification: object) -> bool:
    if not getattr(notification, "call_like", False):
        return False
    state = str(getattr(notification, "call_state_hint", "")).lower()
    return state in {"active", "ongoing", "offhook"}


def _notification_is_missed_call(notification: object) -> bool:
    if not getattr(notification, "call_like", False):
        return False
    searchable = " ".join(
        str(getattr(notification, key, "") or "")
        for key in ("title", "body", "call_state_hint")
    ).lower()
    return "missed" in searchable


if __name__ == "__main__":
    raise SystemExit(main())
