from __future__ import annotations

from linkable_desktop.discovery.models import DiscoveredDevice


def render_device_table(devices: list[DiscoveredDevice]) -> str:
    if not devices:
        return "No devices discovered yet."

    headers = ["#", "Name", "Endpoint", "Version", "Device ID", "Source"]
    rows = [
        [
            str(index),
            device.name,
            device.endpoint,
            device.protocol_version,
            device.device_id,
            device.source.value,
        ]
        for index, device in enumerate(devices, start=1)
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def fmt(row: list[str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row))

    divider = "-+-".join("-" * width for width in widths)
    return "\n".join([fmt(headers), divider, *[fmt(row) for row in rows]])

