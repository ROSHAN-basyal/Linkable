from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from threading import Lock, Thread

from linkable_desktop.ui_qt.native_notifications import close_freedesktop_notification


CallActionCallback = Callable[[str], None]
BluetoothStatusProvider = Callable[[], bool]


class CallNotificationController:
    """Tracks one active native ringing notification and closes it when ringing ends."""

    def __init__(
        self,
        *,
        action_callback: CallActionCallback,
        bluetooth_connected: BluetoothStatusProvider,
    ) -> None:
        self._action_callback = action_callback
        self._bluetooth_connected = bluetooth_connected
        self._notify_send = shutil.which("notify-send") or ""
        self._lock = Lock()
        self._active_key = ""
        self._answered_from_desktop = False
        self._ongoing_shown_key = ""
        self._server_id = 0
        self._process: subprocess.Popen[str] | None = None

    def handle_call_metadata_log(self, message: str) -> None:
        if not self._notify_send or not message.startswith("[call metadata]"):
            return
        if "direction=CALL_DIRECTION_INCOMING" not in message:
            return
        state = _metadata_value(message, "state")
        caller = _metadata_value(message, "caller") or "Unknown caller"
        source = _metadata_value(message, "source") or "Phone call"
        if state != "PHONE_CALL_STATE_RINGING":
            if state == "PHONE_CALL_STATE_OFFHOOK":
                with self._lock:
                    should_show_ongoing = (
                        self._answered_from_desktop
                        and bool(self._active_key)
                        and self._ongoing_shown_key != self._active_key
                    )
                    if should_show_ongoing:
                        self._ongoing_shown_key = self._active_key
                if should_show_ongoing:
                    self._show(source=source, caller=caller, ongoing=True)
                return
            if state == "PHONE_CALL_STATE_IDLE":
                self.close()
            return

        key = f"{source}:{caller}:ringing"
        with self._lock:
            if key == self._active_key:
                return
        self.close()
        with self._lock:
            self._active_key = key
        self._show(source=source, caller=caller)

    def close(self) -> None:
        with self._lock:
            self._active_key = ""
            server_id = self._server_id
            process = self._process
            self._server_id = 0
            self._process = None
            self._answered_from_desktop = False
            self._ongoing_shown_key = ""
        if server_id:
            close_freedesktop_notification(server_id)
        if process is not None and process.poll() is None:
            process.terminate()

    def _show(self, *, source: str, caller: str, ongoing: bool = False) -> None:
        actions = ["--action", "hangup=Hang Up"]
        if not ongoing and self._bluetooth_connected():
            actions = ["--action", "answer=Answer", *actions]
        title = f"Ongoing {source}" if ongoing else f"Incoming {source}"
        command = [
            self._notify_send,
            "--print-id",
            "--app-name",
            "Linkable",
            "--category",
            "call",
            "--urgency",
            "critical",
            "--expire-time",
            "0",
            *actions,
            "--wait",
            title,
            caller,
        ]
        Thread(
            target=self._run,
            args=(command,),
            name="linkable-call-notification",
            daemon=True,
        ).start()

    def _run(self, command: list[str]) -> None:
        try:
            process = subprocess.Popen(
                command,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return
        with self._lock:
            self._process = process
        selected: list[str] = []
        try:
            if process.stdout is not None:
                first_line = process.stdout.readline().strip()
                if first_line.isdigit():
                    with self._lock:
                        self._server_id = int(first_line)
                elif first_line:
                    selected.append(first_line)
                remaining, _ = process.communicate(timeout=3600)
                selected.extend(line.strip() for line in remaining.splitlines() if line.strip())
            else:
                process.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            process.terminate()
            return
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
                    self._server_id = 0
        if selected:
            action = selected[-1].strip()
            if action == "answer":
                with self._lock:
                    self._answered_from_desktop = True
            self._action_callback(action)


def _metadata_value(message: str, key: str) -> str:
    match = re.search(rf"{re.escape(key)}=([^;]+)", message)
    return match.group(1).strip() if match else ""
