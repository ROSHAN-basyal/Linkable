from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from linkable_desktop.proto import common_pb2, input_pb2


@dataclass(frozen=True)
class InputCommandResult:
    success: bool
    detail: str


class DesktopInputController:
    """Executes phone-originated PC control requests through desktop-safe backends."""

    def __init__(self) -> None:
        self.ydotool = shutil.which("ydotool") or ""
        self.wpctl = shutil.which("wpctl") or ""
        self.pactl = shutil.which("pactl") or ""

    def status_lines(self) -> list[str]:
        lines = [
            "Desktop input backend",
            f"ydotool: {self.ydotool or 'not found'}",
            f"wpctl: {self.wpctl or 'not found'}",
            f"pactl: {self.pactl or 'not found'}",
        ]
        if not self.ydotool:
            lines.append("input: install ydotool and run ydotoold with uinput access for Wayland/X11-safe control.")
        if not self.wpctl and not self.pactl:
            lines.append("audio: install PipeWire wpctl or PulseAudio pactl for volume/mic control.")
        return lines

    def handle(self, request: input_pb2.DesktopInputRequest) -> input_pb2.DesktopInputResult:
        result = self.execute(request)
        return input_pb2.DesktopInputResult(
            request_id=request.request_id,
            success=result.success,
            detail=result.detail,
            completed_at=common_pb2.Timestamp(unix_epoch_ms=_timestamp_ms()),
        )

    def execute(self, request: input_pb2.DesktopInputRequest) -> InputCommandResult:
        action = request.action_type
        if action == input_pb2.DESKTOP_INPUT_ACTION_TYPE_TEXT:
            return self._type_text(request.text)
        if action == input_pb2.DESKTOP_INPUT_ACTION_TYPE_KEY_COMBO:
            return self._key_combo(tuple(request.key_combo))
        if action == input_pb2.DESKTOP_INPUT_ACTION_TYPE_POINTER_MOVE:
            return self._mousemove(request.pointer_dx, request.pointer_dy)
        if action == input_pb2.DESKTOP_INPUT_ACTION_TYPE_POINTER_CLICK:
            return self._click(request.pointer_button or 1)
        if action == input_pb2.DESKTOP_INPUT_ACTION_TYPE_POINTER_SCROLL:
            return self._scroll(request.scroll_y)
        if action == input_pb2.DESKTOP_INPUT_ACTION_TYPE_VOLUME_SET:
            return self._set_volume(request.volume_percent)
        if action == input_pb2.DESKTOP_INPUT_ACTION_TYPE_MIC_MUTE_SET:
            return self._set_mic_muted(request.mic_muted)
        return InputCommandResult(False, f"unsupported desktop input action: {action}")

    def _type_text(self, text: str) -> InputCommandResult:
        if not text:
            return InputCommandResult(False, "text is empty")
        if not self.ydotool:
            return InputCommandResult(False, "ydotool is required for keyboard text input")
        return _run((self.ydotool, "type", "--", text))

    def _key_combo(self, combo: tuple[str, ...]) -> InputCommandResult:
        if not combo:
            return InputCommandResult(False, "key combo is empty")
        if not self.ydotool:
            return InputCommandResult(False, "ydotool is required for key combos")
        mapped = tuple(_YDO_KEY_ALIASES.get(key.lower(), key) for key in combo)
        events = tuple(f"{key}:1" for key in mapped) + tuple(f"{key}:0" for key in reversed(mapped))
        return _run((self.ydotool, "key", *events))

    def _mousemove(self, dx: int, dy: int) -> InputCommandResult:
        if not self.ydotool:
            return InputCommandResult(False, "ydotool is required for pointer movement")
        return _run((self.ydotool, "mousemove", "--", str(dx), str(dy)))

    def _click(self, button: int) -> InputCommandResult:
        if not self.ydotool:
            return InputCommandResult(False, "ydotool is required for pointer clicks")
        button_code = {1: "0xC0", 2: "0xC1", 3: "0xC2"}.get(button, "0xC0")
        return _run((self.ydotool, "click", button_code))

    def _scroll(self, delta_y: int) -> InputCommandResult:
        if not self.ydotool:
            return InputCommandResult(False, "ydotool is required for pointer scrolling")
        if delta_y == 0:
            return InputCommandResult(False, "scroll delta is zero")
        button_code = "0xC4" if delta_y > 0 else "0xC5"
        steps = min(abs(delta_y), 12)
        for _ in range(steps):
            result = _run((self.ydotool, "click", button_code))
            if not result.success:
                return result
        return InputCommandResult(True, f"scroll sent: {delta_y}")

    def _set_volume(self, percent: int) -> InputCommandResult:
        clamped = max(0, min(150, percent))
        if self.wpctl:
            return _run((self.wpctl, "set-volume", "@DEFAULT_AUDIO_SINK@", f"{clamped}%"))
        if self.pactl:
            return _run((self.pactl, "set-sink-volume", "@DEFAULT_SINK@", f"{clamped}%"))
        return InputCommandResult(False, "wpctl or pactl is required for speaker volume control")

    def _set_mic_muted(self, muted: bool) -> InputCommandResult:
        value = "1" if muted else "0"
        if self.wpctl:
            return _run((self.wpctl, "set-mute", "@DEFAULT_AUDIO_SOURCE@", value))
        if self.pactl:
            return _run((self.pactl, "set-source-mute", "@DEFAULT_SOURCE@", value))
        return InputCommandResult(False, "wpctl or pactl is required for microphone mute control")


def _run(command: tuple[str, ...]) -> InputCommandResult:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return InputCommandResult(False, str(exc))
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)
    if completed.returncode == 0:
        return InputCommandResult(True, output or "ok")
    return InputCommandResult(False, output or f"exit={completed.returncode}")


def _timestamp_ms() -> int:
    import time

    return int(time.time() * 1000)


_YDO_KEY_ALIASES = {
    "ctrl": "29",
    "control": "29",
    "alt": "56",
    "shift": "42",
    "super": "125",
    "meta": "125",
    "enter": "28",
    "return": "28",
    "esc": "1",
    "escape": "1",
    "tab": "15",
    "space": "57",
    "backspace": "14",
    "delete": "111",
    "up": "103",
    "down": "108",
    "left": "105",
    "right": "106",
}
