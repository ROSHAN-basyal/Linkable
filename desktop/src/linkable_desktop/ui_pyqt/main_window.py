from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from linkable_desktop.app.runtime import DesktopRuntime
from linkable_desktop.config import CONFIG_DIR
from linkable_desktop.proto import calls_pb2, notifications_pb2
from linkable_desktop.ui_qt.call_notifications import CallNotificationController
from linkable_desktop.ui_qt.native_notifications import NativeNotificationAction, NativeNotificationManager
from linkable_desktop.ui_pyqt.constants import tr
from linkable_desktop.ui_pyqt.devices_panel import (
    DeviceNotificationsPage,
    DeviceSettingsPage,
    HomePanel,
    NotificationCenterPage,
)
from linkable_desktop.ui_pyqt.icons import IconButton
from linkable_desktop.ui_pyqt.runtime_bridge import RuntimeBridge
from linkable_desktop.ui_pyqt.theme import size, space
from linkable_desktop.ui_pyqt.toggles import SwitchControl


class MainWindow(QMainWindow):
    """Primary Linkable desktop shell with top service controls and popup-driven navigation."""

    def __init__(self, runtime: DesktopRuntime, bridge: RuntimeBridge, root_dir: Path) -> None:
        super().__init__()
        self.runtime = runtime
        self.bridge = bridge
        self.root_dir = root_dir
        self.home_panel: HomePanel | None = None
        self.current_private_page: QWidget | None = None
        self.logs_visible = False
        self._service_change_in_progress = False
        self._native_notification_fingerprints: dict[str, str] = {}
        self._native_notifications_by_id: dict[str, object] = {}
        self._native_active_ringing_call_ids: set[str] = set()
        self._native_desktop_answered_call_ids: set[str] = set()
        self._native_ongoing_call_ids: set[str] = set()
        self._native_clipboard_ids: set[str] = set()
        self._native_notifications = NativeNotificationManager(
            icon_dir=CONFIG_DIR / "notification-icons",
            action_callback=lambda notification_id, action: self.bridge.native_notification_action.emit(notification_id, action),
            call_answer_allowed=self.runtime.active_phone_bluetooth_connected,
        )
        self._call_notifications = CallNotificationController(
            action_callback=self.bridge.native_call_action.emit,
            bluetooth_connected=self.runtime.active_phone_bluetooth_connected,
        )
        self.setWindowTitle(tr("app.title"))
        self.setMinimumSize(size("window_min_w"), size("window_min_h"))
        self.resize(size("window_w"), size("window_h"))
        self._build_ui()
        self._connect_signals()
        self._set_service_enabled(True)

    def _build_ui(self) -> None:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(space("xl"), space("panel_x"), space("xl"), space("lg"))
        root.setSpacing(space("md"))

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(space("card_x"), space("sm"), space("card_x"), space("sm"))
        top_layout.setSpacing(space("md"))
        brand = QVBoxLayout()
        title = QLabel(tr("app.title"))
        title.setObjectName("AppTitle")
        subtitle = QLabel(tr("app.subtitle"))
        subtitle.setObjectName("AppSubtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        top_layout.addLayout(brand, 1)

        self.service_toggle = SwitchControl(tr("main.service.toggle"))
        self.service_toggle.toggled.connect(self._set_service_enabled)
        top_layout.addWidget(self.service_toggle)
        top_layout.addWidget(self._meta_group(tr("main.endpoint"), "endpoint_value"))
        top_layout.addWidget(self._meta_group(tr("main.device_id"), "device_id_value"))
        self.notification_center_button = IconButton(
            "icon-notifications.svg",
            tr("notifications.center.open"),
            object_name="IconButtonMuted",
        )
        self.notification_center_button.clicked.connect(self._show_notification_center)
        top_layout.addWidget(self.notification_center_button)
        self.refresh_button = IconButton("icon-refresh.svg", tr("main.refresh"), object_name="RefreshButton")
        self.refresh_button.clicked.connect(self._refresh_service)
        top_layout.addWidget(self.refresh_button)
        root.addWidget(top_bar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("ContentStack")
        root.addWidget(self.stack, 1)
        self.home_panel = HomePanel(self.runtime)
        self.home_panel.settings_requested.connect(self._show_device_settings)
        self.home_panel.notifications_requested.connect(self._show_device_notifications)
        self.stack.addWidget(self.home_panel)

        log_row = QHBoxLayout()
        log_row.addStretch(1)
        self.log_button = QPushButton(tr("main.logs.show"))
        self.log_button.clicked.connect(self._toggle_logs)
        log_row.addWidget(self.log_button)
        root.addLayout(log_row)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(500)
        self.log_view.setMaximumHeight(size("log_max_h"))
        self.log_view.hide()
        root.addWidget(self.log_view)
        self.setCentralWidget(container)
        self._update_service_metadata(False)

    def _meta_group(self, label: str, attr_name: str) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(space("none"), space("none"), space("none"), space("none"))
        layout.setSpacing(space("xs"))
        title = QLabel(label)
        title.setObjectName("TopMetaLabel")
        value = QLabel(tr("main.service.off"))
        value.setObjectName("TopMetaValue")
        value.setMinimumWidth(170)
        setattr(self, attr_name, value)
        layout.addWidget(title)
        layout.addWidget(value)
        return box

    def _connect_signals(self) -> None:
        self.bridge.log_received.connect(self._append_log)
        self.bridge.devices_changed.connect(self._refresh_home)
        self.bridge.notifications_changed.connect(self._refresh_notifications)
        self.bridge.clipboard_changed.connect(self._refresh_clipboard_notifications)
        self.bridge.shared_apps_changed.connect(self._refresh_home)
        self.bridge.phone_files_changed.connect(self._refresh_home)
        self.bridge.contacts_changed.connect(self._refresh_home)
        self.bridge.code_requested.connect(self._handle_code_request)
        self.bridge.native_notification_action.connect(self._handle_native_notification_action)
        self.bridge.native_call_action.connect(self._handle_native_call_action)

    def _set_service_enabled(self, enabled: bool) -> None:
        if self._service_change_in_progress:
            return
        self._service_change_in_progress = True
        try:
            if enabled:
                try:
                    self.runtime.start()
                except Exception as exc:  # noqa: BLE001
                    self._set_toggle_checked(False)
                    self._update_service_metadata(False)
                    QMessageBox.critical(self, tr("app.title"), str(exc))
                    return
                self._set_toggle_checked(True)
                self._update_service_metadata(True)
            else:
                self.runtime.stop()
                self._set_toggle_checked(False)
                self._update_service_metadata(False)
            self._refresh_home()
        finally:
            self._service_change_in_progress = False

    def _set_toggle_checked(self, checked: bool) -> None:
        self.service_toggle.blockSignals(True)
        self.service_toggle.setChecked(checked)
        self.service_toggle.blockSignals(False)

    def _update_service_metadata(self, running: bool) -> None:
        if running:
            self.endpoint_value.setText(self.runtime.endpoint_summary)
            self.device_id_value.setText(self.runtime.device_id)
        else:
            self.endpoint_value.setText(tr("main.service.off"))
            self.device_id_value.setText(tr("main.service.off"))

    def _refresh_home(self) -> None:
        if self.home_panel is not None:
            self.home_panel.refresh()

    def _refresh_notifications(self) -> None:
        notifications = self.runtime.notifications()
        current_ids = {notification.notification_id for notification in notifications}
        tracked_call_ids = self._native_active_ringing_call_ids | self._native_ongoing_call_ids
        for notification_id in list(tracked_call_ids):
            if notification_id not in current_ids:
                self._native_notifications.close(notification_id)
                self._native_active_ringing_call_ids.discard(notification_id)
                self._native_desktop_answered_call_ids.discard(notification_id)
                self._native_ongoing_call_ids.discard(notification_id)
                self._native_notification_fingerprints.pop(notification_id, None)
                self._native_notifications_by_id.pop(notification_id, None)
        for notification in notifications:
            if _notification_is_active_call(notification):
                self._native_notifications_by_id[notification.notification_id] = notification
                if _notification_is_ringing_call(notification):
                    if notification.notification_id not in self._native_active_ringing_call_ids:
                        self._native_active_ringing_call_ids.add(notification.notification_id)
                        self._native_notifications.show(notification)
                    continue
                if notification.notification_id in self._native_active_ringing_call_ids:
                    self._native_notifications.close(notification.notification_id)
                    self._native_active_ringing_call_ids.discard(notification.notification_id)
                    self._native_notification_fingerprints.pop(notification.notification_id, None)
                if (
                    notification.notification_id in self._native_desktop_answered_call_ids
                    and _notification_is_ongoing_call(notification)
                    and notification.notification_id not in self._native_ongoing_call_ids
                ):
                    self._native_ongoing_call_ids.add(notification.notification_id)
                    self._native_notifications.show(notification)
                    continue
                if not _notification_is_missed_call(notification):
                    continue
            fingerprint = _native_notification_fingerprint(notification)
            previous_fingerprint = self._native_notification_fingerprints.get(notification.notification_id)
            if previous_fingerprint != fingerprint:
                if previous_fingerprint is not None:
                    self._native_notifications.close(notification.notification_id)
                self._native_notification_fingerprints[notification.notification_id] = fingerprint
                self._native_notifications_by_id[notification.notification_id] = notification
                self._native_notifications.show(notification, silent=not _notification_is_fresh_for_popup(notification))
        if isinstance(self.current_private_page, (DeviceNotificationsPage, NotificationCenterPage)):
            self.current_private_page.refresh()

    def _refresh_clipboard_notifications(self) -> None:
        for update in self.runtime.clipboard_updates():
            update_id = update.update_id or hashlib.sha256(update.text.encode()).hexdigest()
            if update_id in self._native_clipboard_ids:
                continue
            self._native_clipboard_ids.add(update_id)
            self._native_notifications.show_clipboard(update)

    def _refresh_service(self) -> None:
        if self.runtime.is_running:
            self.runtime.refresh()
            self._update_service_metadata(True)
        self._refresh_home()
        self._refresh_notifications()

    def _show_device_settings(self, device: object) -> None:
        page = DeviceSettingsPage(self.runtime, device)
        page.back_requested.connect(self._show_home)
        self._show_private_page(page)

    def _show_device_notifications(self, device: object) -> None:
        page = DeviceNotificationsPage(self.runtime, device)
        page.back_requested.connect(self._show_home)
        self._show_private_page(page)

    def _show_notification_center(self) -> None:
        page = NotificationCenterPage(self.runtime)
        page.back_requested.connect(self._show_home)
        self._show_private_page(page)

    def _show_private_page(self, page: QWidget) -> None:
        self._remove_private_page()
        self.current_private_page = page
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def _show_home(self) -> None:
        self.stack.setCurrentIndex(0)
        self._remove_private_page()
        if self.home_panel is not None:
            self.home_panel.clear_status()
        self._refresh_home()

    def _remove_private_page(self) -> None:
        if self.current_private_page is not None:
            self.stack.removeWidget(self.current_private_page)
            self.current_private_page.deleteLater()
            self.current_private_page = None

    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        self._maybe_show_native_call(message)
        transfer_status = self._transfer_status_from_log(message)
        if transfer_status and self.home_panel is not None:
            self.home_panel.show_status(transfer_status)

    def _maybe_show_native_call(self, message: str) -> None:
        self._call_notifications.handle_call_metadata_log(message)

    def _run_native_call_notification(self, command: list[str]) -> None:
        try:
            completed = subprocess.run(command, text=True, capture_output=True, timeout=3600, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return
        selected = completed.stdout.strip().splitlines()
        if selected:
            self.bridge.native_call_action.emit(selected[-1].strip())

    def _transfer_status_from_log(self, message: str) -> str | None:
        if message.startswith("Queued file for phone transfer:"):
            return "File queued for phone transfer. Waiting for the phone session."
        if message.startswith("Sending file to "):
            return "Sending file to phone..."
        if message.startswith("[file transfer ok]"):
            return "File sent to phone successfully."
        if message.startswith("[file transfer failed]"):
            return message
        if message.startswith("[file receive accepted]"):
            return "Receiving file from phone..."
        if message.startswith("[file receive ok]"):
            return "File received from phone successfully."
        if message.startswith("[file receive failed]"):
            return message
        if message.startswith("[phone file pull ok]"):
            return "Phone file copy request accepted."
        if message.startswith("[phone file pull failed]"):
            return message
        return None

    def _toggle_logs(self) -> None:
        self.logs_visible = not self.logs_visible
        self.log_view.setVisible(self.logs_visible)
        self.log_button.setText(tr("main.logs.hide") if self.logs_visible else tr("main.logs.show"))

    def _handle_code_request(self, result: object) -> None:
        queue = result
        code, ok = QInputDialog.getText(self, tr("pairing.title"), tr("pairing.code"))
        queue.put(code.strip() if ok else "")

    def _handle_native_notification_action(self, notification_id: str, action: NativeNotificationAction) -> None:
        if action.kind == "clipboard_copy":
            QApplication.clipboard().setText(action.payload)
            self._append_log("[clipboard] Copied mobile clipboard text to desktop clipboard.")
            return
        notification = self._native_notifications_by_id.get(notification_id)
        if action.kind == "answer" and notification is not None and getattr(notification, "call_like", False):
            self._native_desktop_answered_call_ids.add(notification_id)
        if action.kind in {"hangup", "decline"}:
            self._native_notifications.close(notification_id)
        if action.kind == "reply":
            if notification is None:
                self._append_log(f"[native notification] Reply requested for expired notification {notification_id}")
                return
            reply_text, ok = QInputDialog.getText(
                self,
                tr("notifications.reply"),
                f"{getattr(notification, 'app_name', '') or getattr(notification, 'package_name', '')}\n"
                f"{getattr(notification, 'title', '')}\n\nReply:",
            )
            if ok and reply_text.strip():
                self.runtime.queue_notification_reply(notification_id, action.action_id, reply_text)
            return
        self.runtime.queue_notification_action(notification_id, action.action_id)

    def _handle_native_call_action(self, action: str) -> None:
        if action == "answer":
            self.runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_ACCEPT)
        elif action == "decline":
            self.runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_REJECT)
        elif action == "hangup":
            self.runtime.queue_call_control(calls_pb2.CALL_CONTROL_ACTION_HANGUP)

    def closeEvent(self, event: object) -> None:
        self.runtime.stop()
        super().closeEvent(event)


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
