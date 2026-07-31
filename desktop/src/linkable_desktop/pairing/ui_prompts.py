from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Iterable


@dataclass(slots=True)
class ConsolePrompts:
    _lock: Lock = field(default_factory=Lock)

    def confirm_pairing(self, phone_name: str, device_id: str, address: str) -> bool:
        with self._lock:
            while True:
                answer = input(
                    f"Pairing request from '{phone_name}' ({device_id}) at {address}. Allow? [y/N]: "
                ).strip().lower()
                if answer in {"y", "yes"}:
                    return True
                if answer in {"", "n", "no"}:
                    return False

    def prompt_code(self) -> str:
        with self._lock:
            return input("Enter the 6-digit code shown on the phone: ").strip()

    def notify(self, message: str) -> None:
        with self._lock:
            print(message)

    def record_trusted_session_started(self, device_name: str, device_id: str, endpoint: str) -> None:
        return None

    def record_trusted_session_closed(self, device_id: str) -> None:
        return None

    def record_bluetooth_status(self, device_id: str, status: object) -> None:
        return None

    def record_notification(self, notification: object) -> None:
        return None

    def record_notification_removed(self, notification_id: str) -> None:
        return None

    def record_shared_apps(self, snapshot: object) -> None:
        return None

    def record_shared_app_launch_result(self, result: object) -> None:
        return None

    def record_phone_file_list(self, response: object) -> None:
        return None

    def record_phone_file_pull_result(self, result: object) -> None:
        return None

    def record_file_received(self, result: object) -> None:
        return None

    def record_contacts(self, response: object) -> None:
        return None

    def record_recent_contacts(self, response: object) -> None:
        return None

    def record_camera_capability(self, response: object) -> None:
        return None

    def record_camera_start_result(self, result: object) -> None:
        return None

    def record_camera_stop_result(self, result: object) -> None:
        return None

    def record_camera_status(self, event: object) -> None:
        return None

    def record_camera_frame(self, frame: object) -> None:
        return None

    def record_clipboard_update(self, update: object) -> None:
        return None

    def prompt_notification_reply(
        self,
        app_name: str,
        title: str,
        actions: Iterable[tuple[str, str]],
    ) -> tuple[str, str] | None:
        actions = list(actions)
        if not actions:
            return None
        with self._lock:
            print(f"Reply-capable notification from {app_name}: {title}")
            for action_id, action_title in actions:
                print(f"  action {action_id}: {action_title or 'Reply'}")
            action_id = input("Reply action id, or blank to skip: ").strip()
            if not action_id:
                return None
            if action_id not in {candidate for candidate, _ in actions}:
                print(f"Unknown reply action id: {action_id}")
                return None
            reply_text = input("Reply text: ").strip()
            if not reply_text:
                return None
            return action_id, reply_text
