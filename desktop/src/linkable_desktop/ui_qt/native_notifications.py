from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from typing import Callable

from linkable_desktop.proto import clipboard_pb2, notifications_pb2


@dataclass(frozen=True)
class NativeNotificationAction:
    kind: str
    action_id: str
    payload: str = ""


NativeActionCallback = Callable[[str, NativeNotificationAction], None]
CallAnswerAllowed = Callable[[], bool]


class NativeNotificationManager:
    def __init__(
        self,
        *,
        icon_dir: Path,
        action_callback: NativeActionCallback,
        call_answer_allowed: CallAnswerAllowed = lambda: True,
    ) -> None:
        self.icon_dir = icon_dir
        self.action_callback = action_callback
        self.call_answer_allowed = call_answer_allowed
        self.notify_send = shutil.which("notify-send") or ""
        self._lock = Lock()
        self._notification_server_ids: dict[str, int] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}

    @property
    def available(self) -> bool:
        return bool(self.notify_send)

    def show(self, notification: notifications_pb2.NotificationPosted, *, silent: bool = False) -> None:
        if not self.available:
            return
        icon_path = self.write_icon(notification)
        app_name = notification.app_name or notification.package_name or "Android"
        summary = f"{app_name}: {notification.title or 'Notification'}"
        body = notification.body or notification.call_state_hint or notification.package_name
        action_routes = self.action_routes(notification)
        urgency = "low" if silent or notification.silent else ("critical" if notification.call_like else "normal")
        command = [
            self.notify_send,
            "--print-id",
            "--app-name",
            app_name,
            "--category",
            "call" if notification.call_like else "im.received",
            "--urgency",
            urgency,
            "--expire-time",
            "0",
        ]
        if silent:
            command.extend(
                [
                    "--hint",
                    "boolean:suppress-sound:true",
                    "--hint",
                    "string:sound-name:silent",
                ]
            )
        if icon_path:
            command.extend(["--icon", icon_path])
        for action_key, route in action_routes.items():
            command.extend(["--action", f"{action_key}={self.action_label(route, notification)}"])
        if action_routes:
            command.append("--wait")
        command.extend([summary, body])
        Thread(
            target=self.run_notification,
            args=(notification.notification_id, command, action_routes),
            name=f"linkable-native-notification-{notification.notification_id[:12]}",
            daemon=True,
        ).start()

    def show_clipboard(self, update: clipboard_pb2.ClipboardUpdate) -> None:
        """Show an actionable native popup for a mobile clipboard update."""

        if not self.available or not update.text:
            return
        title = "Mobile clipboard copied"
        source = update.source_device_name or "Phone"
        body = _preview_text(update.text)
        notification_id = f"clipboard:{update.update_id or hashlib.sha256(update.text.encode()).hexdigest()[:16]}"
        command = [
            self.notify_send,
            "--print-id",
            "--app-name",
            "Linkable",
            "--category",
            "transfer",
            "--urgency",
            "normal",
            "--expire-time",
            "0",
            "--action",
            "copy=Copy",
            "--wait",
            f"{title} from {source}",
            body,
        ]
        routes = {
            "copy": NativeNotificationAction(
                kind="clipboard_copy",
                action_id=update.update_id,
                payload=update.text,
            )
        }
        Thread(
            target=self.run_notification,
            args=(notification_id, command, routes),
            name=f"linkable-clipboard-notification-{notification_id[-12:]}",
            daemon=True,
        ).start()

    def close(self, notification_id: str) -> None:
        """Close a native notification shown by this manager when the server supports IDs."""

        with self._lock:
            server_id = self._notification_server_ids.pop(notification_id, 0)
            process = self._processes.pop(notification_id, None)
        if server_id:
            close_freedesktop_notification(server_id)
        if process is not None and process.poll() is None:
            process.terminate()

    def write_icon(self, notification: notifications_pb2.NotificationPosted) -> str:
        if not notification.app_icon_png:
            return ""
        self.icon_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(notification.app_icon_png).hexdigest()[:24]
        path = self.icon_dir / f"{digest}.png"
        if not path.exists():
            path.write_bytes(notification.app_icon_png)
        return str(path)

    def action_routes(self, notification: notifications_pb2.NotificationPosted) -> dict[str, NativeNotificationAction]:
        routes: dict[str, NativeNotificationAction] = {}
        reply_action = next((action for action in notification.actions if action.supports_remote_input), None)
        if reply_action is not None:
            routes["reply"] = NativeNotificationAction(kind="reply", action_id=reply_action.action_id)
        if notification.call_like:
            if self.call_answer_allowed():
                answer = self._plain_call_action(notification, notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_ANSWER_CALL)
                if answer is not None:
                    routes["answer"] = NativeNotificationAction(kind="answer", action_id=answer.action_id)
            hangup = self._plain_call_action(notification, notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_HANG_UP_CALL)
            if hangup is None:
                hangup = self._plain_call_action(notification, notifications_pb2.NOTIFICATION_ACTION_SEMANTIC_DECLINE_CALL)
            if hangup is not None:
                routes["hangup"] = NativeNotificationAction(kind="hangup", action_id=hangup.action_id)
        return routes

    def _plain_call_action(
        self,
        notification: notifications_pb2.NotificationPosted,
        semantic: int,
    ) -> notifications_pb2.NotificationAction | None:
        return next(
            (
                candidate
                for candidate in notification.actions
                if candidate.supports_plain_intent and candidate.semantic == semantic
            ),
            None,
        )

    def action_label(self, route: NativeNotificationAction, notification: notifications_pb2.NotificationPosted) -> str:
        if route.kind == "reply":
            return "Reply"
        if route.kind == "answer":
            return "Answer on Laptop"
        if route.kind == "hangup":
            return "Hang Up"
        return notification.app_name or "Open"

    def run_notification(
        self,
        notification_id: str,
        command: list[str],
        action_routes: dict[str, NativeNotificationAction],
    ) -> None:
        timeout = 3600 if action_routes else 10
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
            self._processes[notification_id] = process
        selected: list[str] = []
        try:
            if process.stdout is not None:
                first_line = process.stdout.readline().strip()
                if first_line.isdigit():
                    with self._lock:
                        self._notification_server_ids[notification_id] = int(first_line)
                elif first_line:
                    selected.append(first_line)
                remaining, _ = process.communicate(timeout=timeout)
                selected.extend(line.strip() for line in remaining.splitlines() if line.strip())
            else:
                process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.terminate()
            return
        finally:
            with self._lock:
                self._processes.pop(notification_id, None)
                if process.poll() is not None:
                    self._notification_server_ids.pop(notification_id, None)
        if not selected:
            return
        route = action_routes.get(selected[-1].strip())
        if route is not None:
            self.action_callback(notification_id, route)


def close_freedesktop_notification(server_id: int) -> None:
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return
    try:
        subprocess.run(
            (
                gdbus,
                "call",
                "--session",
                "--dest",
                "org.freedesktop.Notifications",
                "--object-path",
                "/org/freedesktop/Notifications",
                "--method",
                "org.freedesktop.Notifications.CloseNotification",
                str(server_id),
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def copy_text_to_desktop_clipboard(text: str) -> bool:
    """Copy text outside the GUI process using common Linux clipboard helpers."""

    helpers = (
        ("wl-copy",),
        ("xclip", "-selection", "clipboard"),
        ("xsel", "--clipboard", "--input"),
    )
    for command in helpers:
        executable = shutil.which(command[0])
        if not executable:
            continue
        try:
            completed = subprocess.run(
                (executable, *command[1:]),
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3,
                check=False,
            )
            if completed.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def _preview_text(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= 180:
        return collapsed
    return f"{collapsed[:177]}..."
