from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from .device_record import TrustedDeviceRecord


@dataclass(slots=True)
class TrustStore:
    path: Path
    _lock: Lock = field(default_factory=Lock)

    def _load(self) -> dict[str, TrustedDeviceRecord]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return {
            entry["device_id"]: TrustedDeviceRecord.from_json(entry)
            for entry in raw.get("devices", [])
        }

    def _save(self, devices: dict[str, TrustedDeviceRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "devices": [record.to_json() for record in sorted(devices.values(), key=lambda item: item.device_name.lower())]
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def upsert(self, record: TrustedDeviceRecord) -> None:
        with self._lock:
            devices = self._load()
            devices[record.device_id] = record
            self._save(devices)

    def get(self, device_id: str) -> TrustedDeviceRecord | None:
        with self._lock:
            return self._load().get(device_id)

    def list_records(self) -> list[TrustedDeviceRecord]:
        with self._lock:
            return list(self._load().values())

    def remove(self, device_id: str) -> bool:
        with self._lock:
            devices = self._load()
            removed = devices.pop(device_id, None)
            if removed is None:
                return False
            self._save(devices)
            return True
