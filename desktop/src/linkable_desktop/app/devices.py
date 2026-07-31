from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from linkable_desktop.trust.device_record import TrustedDeviceRecord


class DeviceAvailability(str, Enum):
    """Current desktop-side availability state for a paired phone."""

    CONNECTED = "connected"
    UNAVAILABLE = "unavailable"
    MANUALLY_DISCONNECTED = "manually_disconnected"


@dataclass(frozen=True, slots=True)
class ActiveDevice:
    """Live LAN session metadata observed from trusted phone reconnects."""

    device_id: str
    device_name: str
    endpoint: str
    last_seen_epoch: float


@dataclass(frozen=True, slots=True)
class DeviceViewModel:
    """The device data shape consumed by the Devices panel."""

    device_id: str
    device_name: str
    endpoint: str
    paired_at_epoch_ms: int
    availability: DeviceAvailability
    bluetooth_connected: bool = False

    @property
    def is_connected(self) -> bool:
        return self.availability == DeviceAvailability.CONNECTED

    @property
    def can_disconnect(self) -> bool:
        return self.availability == DeviceAvailability.CONNECTED

    @property
    def can_allow_reconnect(self) -> bool:
        return self.availability == DeviceAvailability.MANUALLY_DISCONNECTED


def build_device_models(
    records: list[TrustedDeviceRecord],
    active_devices: dict[str, ActiveDevice],
    manually_disconnected_ids: set[str],
    bluetooth_connected_ids: set[str] | None = None,
) -> list[DeviceViewModel]:
    """Merge trusted devices with runtime session state for display."""

    bluetooth_ids = bluetooth_connected_ids or set()
    models: list[DeviceViewModel] = []
    for record in sorted(records, key=lambda item: item.device_name.lower()):
        active = active_devices.get(record.device_id)
        if active is not None:
            availability = DeviceAvailability.CONNECTED
            endpoint = active.endpoint
        elif record.device_id in manually_disconnected_ids:
            availability = DeviceAvailability.MANUALLY_DISCONNECTED
            endpoint = ""
        else:
            availability = DeviceAvailability.UNAVAILABLE
            endpoint = ""
        models.append(
            DeviceViewModel(
                device_id=record.device_id,
                device_name=record.device_name,
                endpoint=endpoint,
                paired_at_epoch_ms=record.paired_at_epoch_ms,
                availability=availability,
                bluetooth_connected=record.device_id in bluetooth_ids,
            )
        )
    return models
