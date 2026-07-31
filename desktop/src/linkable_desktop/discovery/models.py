from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from time import time


class DiscoverySource(str, Enum):
    MDNS = "mdns"
    DIRECT_CONNECT = "direct_connect"


@dataclass(slots=True)
class DiscoveredDevice:
    name: str
    host: str
    port: int
    protocol_version: str = "unknown"
    device_id: str = "unknown"
    service_name: str | None = None
    source: DiscoverySource = DiscoverySource.MDNS
    discovered_at: float = field(default_factory=time)

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def stable_key(self) -> str:
        if self.service_name:
            return self.service_name
        return f"{self.source.value}:{self.endpoint}:{self.device_id}"

