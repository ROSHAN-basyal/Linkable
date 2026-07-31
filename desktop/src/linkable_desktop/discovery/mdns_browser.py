from __future__ import annotations

import socket
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from .models import DiscoveredDevice, DiscoverySource

def _load_zeroconf() -> tuple[Any, Any]:
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
        raise RuntimeError(
            "zeroconf is not installed. Install desktop requirements before using discovery browsing."
        ) from exc
    return ServiceBrowser, Zeroconf


def _decode_property(value: bytes | str | None) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _service_addresses(info: Any) -> list[str]:
    addresses: list[str] = []
    for packed in getattr(info, "addresses", []) or []:
        try:
            addresses.append(socket.inet_ntoa(packed))
        except OSError:
            continue
    return addresses


@dataclass(slots=True)
class DiscoveryRegistry:
    _devices: dict[str, DiscoveredDevice] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def upsert(self, device: DiscoveredDevice) -> None:
        with self._lock:
            self._devices[device.stable_key] = device

    def remove(self, stable_key: str) -> None:
        with self._lock:
            self._devices.pop(stable_key, None)

    def snapshot(self) -> list[DiscoveredDevice]:
        with self._lock:
            return sorted(self._devices.values(), key=lambda device: (device.name.lower(), device.endpoint))


class MdnsServiceListener:
    def __init__(self, registry: DiscoveryRegistry) -> None:
        self.registry = registry

    def add_service(self, zeroconf: Any, service_type: str, name: str) -> None:
        self._update_from_name(zeroconf, service_type, name)

    def update_service(self, zeroconf: Any, service_type: str, name: str) -> None:
        self._update_from_name(zeroconf, service_type, name)

    def remove_service(self, zeroconf: Any, service_type: str, name: str) -> None:
        self.registry.remove(name)

    def ingest_service_info(self, info: Any) -> DiscoveredDevice | None:
        addresses = _service_addresses(info)
        if not addresses:
            return None
        properties = getattr(info, "properties", {}) or {}
        device = DiscoveredDevice(
            name=_decode_property(properties.get(b"device_name")) or getattr(info, "name", "unknown"),
            host=addresses[0],
            port=int(getattr(info, "port", 0)),
            protocol_version=_decode_property(properties.get(b"protocol_version")),
            device_id=_decode_property(properties.get(b"device_id")),
            service_name=getattr(info, "name", None),
            source=DiscoverySource.MDNS,
        )
        self.registry.upsert(device)
        return device

    def _update_from_name(self, zeroconf: Any, service_type: str, name: str) -> None:
        info = zeroconf.get_service_info(service_type, name)
        if info is None:
            return
        self.ingest_service_info(info)


@dataclass(slots=True)
class DiscoveryBrowserController:
    service_type: str
    registry: DiscoveryRegistry = field(default_factory=DiscoveryRegistry)
    zeroconf: Any | None = None
    browser: Any | None = None
    listener: MdnsServiceListener | None = None

    def start(self) -> None:
        if self.zeroconf is not None:
            return
        ServiceBrowser, Zeroconf = _load_zeroconf()
        self.zeroconf = Zeroconf()
        self.listener = MdnsServiceListener(self.registry)
        self.browser = ServiceBrowser(self.zeroconf, self.service_type, self.listener)

    def stop(self) -> None:
        if self.browser is not None:
            cancel = getattr(self.browser, "cancel", None)
            if callable(cancel):
                cancel()
        if self.zeroconf is not None:
            self.zeroconf.close()
        self.browser = None
        self.zeroconf = None
        self.listener = None
