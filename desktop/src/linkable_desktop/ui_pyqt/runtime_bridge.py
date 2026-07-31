from __future__ import annotations

from queue import Empty, Queue

from PyQt6.QtCore import QObject, pyqtSignal


class RuntimeBridge(QObject):
    """Converts runtime callbacks from worker threads into Qt signals."""

    log_received = pyqtSignal(str)
    devices_changed = pyqtSignal()
    notifications_changed = pyqtSignal()
    clipboard_changed = pyqtSignal()
    shared_apps_changed = pyqtSignal()
    phone_files_changed = pyqtSignal()
    contacts_changed = pyqtSignal()
    code_requested = pyqtSignal(object)
    native_notification_action = pyqtSignal(str, object)
    native_call_action = pyqtSignal(str)

    def prompt_code(self) -> str:
        result: Queue[str] = Queue(maxsize=1)
        self.code_requested.emit(result)
        try:
            return result.get(timeout=120)
        except Empty:
            return ""
