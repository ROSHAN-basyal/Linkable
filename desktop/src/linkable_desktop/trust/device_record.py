from __future__ import annotations

import base64
from dataclasses import asdict, dataclass


@dataclass(slots=True)
class TrustedDeviceRecord:
    device_id: str
    device_name: str
    public_key_b64: str
    paired_at_epoch_ms: int

    @property
    def public_key_bytes(self) -> bytes:
        return base64.b64decode(self.public_key_b64.encode("ascii"))

    @classmethod
    def from_public_key(
        cls,
        *,
        device_id: str,
        device_name: str,
        public_key_bytes: bytes,
        paired_at_epoch_ms: int,
    ) -> "TrustedDeviceRecord":
        return cls(
            device_id=device_id,
            device_name=device_name,
            public_key_b64=base64.b64encode(public_key_bytes).decode("ascii"),
            paired_at_epoch_ms=paired_at_epoch_ms,
        )

    def to_json(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, object]) -> "TrustedDeviceRecord":
        return cls(
            device_id=str(data["device_id"]),
            device_name=str(data["device_name"]),
            public_key_b64=str(data["public_key_b64"]),
            paired_at_epoch_ms=int(data["paired_at_epoch_ms"]),
        )

