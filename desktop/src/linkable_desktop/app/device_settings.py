from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from linkable_desktop.config import CONFIG_DIR


DEVICE_SETTINGS_PATH = CONFIG_DIR / "device_settings.json"


@dataclass(frozen=True, slots=True)
class DesktopDeviceSettings:
    """Persisted desktop-only settings for one trusted phone."""

    camera_route_lan: bool = True
    control_input_enabled: bool = False
    control_keyboard_enabled: bool = True
    control_mouse_enabled: bool = True
    control_commands_enabled: bool = False


class DeviceSettingsStore:
    """Small JSON store for per-device desktop settings."""

    def __init__(self, path: Path = DEVICE_SETTINGS_PATH) -> None:
        self.path = path
        self._lock = Lock()

    def get(self, device_id: str) -> DesktopDeviceSettings:
        with self._lock:
            raw = self._load().get(device_id, {})
        return _settings_from_json(raw)

    def set_value(self, device_id: str, key: str, value: bool) -> DesktopDeviceSettings:
        if key not in DesktopDeviceSettings.__dataclass_fields__:
            raise KeyError(f"unknown device setting: {key}")
        with self._lock:
            data = self._load()
            current = asdict(_settings_from_json(data.get(device_id, {})))
            current[key] = bool(value)
            data[device_id] = current
            self._save(data)
        return _settings_from_json(current)

    def remove(self, device_id: str) -> bool:
        with self._lock:
            data = self._load()
            existed = data.pop(device_id, None) is not None
            if existed:
                self._save(data)
        return existed

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        devices = raw.get("devices", {})
        if not isinstance(devices, dict):
            return {}
        return {
            str(device_id): settings
            for device_id, settings in devices.items()
            if isinstance(settings, dict)
        }

    def _save(self, devices: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"devices": devices}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _settings_from_json(data: dict[str, Any]) -> DesktopDeviceSettings:
    defaults = DesktopDeviceSettings()
    values = asdict(defaults)
    for key in values:
        if key in data:
            values[key] = bool(data[key])
    return DesktopDeviceSettings(**values)
