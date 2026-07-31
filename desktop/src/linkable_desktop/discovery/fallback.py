from __future__ import annotations

from dataclasses import dataclass

from .models import DiscoveredDevice, DiscoverySource


@dataclass(slots=True)
class DirectConnectCandidate:
    host: str
    port: int

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    def to_device(self, *, protocol_version: str = "manual", device_name: str = "Direct Connect") -> DiscoveredDevice:
        return DiscoveredDevice(
            name=device_name,
            host=self.host,
            port=self.port,
            protocol_version=protocol_version,
            device_id="unverified",
            source=DiscoverySource.DIRECT_CONNECT,
        )


def parse_direct_connect_endpoint(raw: str, default_port: int = 37891) -> DirectConnectCandidate:
    value = raw.strip()
    if not value:
        raise ValueError("endpoint is empty")

    if value.startswith("[") and "]" in value:
        host, _, tail = value[1:].partition("]")
        if not host:
            raise ValueError("missing IPv6 host")
        if tail.startswith(":"):
            port = int(tail[1:])
        elif tail == "":
            port = default_port
        else:
            raise ValueError("invalid IPv6 endpoint")
        return DirectConnectCandidate(host=host, port=port)

    if value.count(":") == 1:
        host, port_text = value.rsplit(":", 1)
        if host and port_text:
            return DirectConnectCandidate(host=host, port=int(port_text))

    if ":" in value:
        return DirectConnectCandidate(host=value, port=default_port)
    return DirectConnectCandidate(host=value, port=default_port)
