from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from linkable_desktop.config import CONFIG_DIR
from linkable_desktop.secure_storage import atomic_write_private, enforce_private_file


SAFE_WIFI_POLICY_PATH = CONFIG_DIR / "desktop_safe_wifi.json"


@dataclass(frozen=True, slots=True)
class DesktopSafeWifiNetwork:
    """One desktop-side Wi-Fi network that may be allowed for Linkable sessions."""

    ssid: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class DesktopSafeWifiPolicy:
    """Desktop-side safe-Wi-Fi policy with explicit network approval by default."""

    allow_all_wifi: bool
    current_ssid: str
    networks: tuple[DesktopSafeWifiNetwork, ...]


class DesktopSafeWifiStore:
    """Persists and evaluates desktop safe-Wi-Fi policy without privileged commands."""

    def load(self) -> DesktopSafeWifiPolicy:
        data = self._read()
        return DesktopSafeWifiPolicy(
            allow_all_wifi=bool(data.get("allow_all_wifi", False)),
            current_ssid=current_wifi_ssid(),
            networks=tuple(
                DesktopSafeWifiNetwork(ssid=str(item.get("ssid", "")), enabled=bool(item.get("enabled", True)))
                for item in data.get("networks", [])
                if str(item.get("ssid", "")).strip()
            ),
        )

    def set_allow_all_wifi(self, allow_all: bool) -> bool:
        data = self._read()
        if bool(data.get("allow_all_wifi", False)) == allow_all:
            return False
        data["allow_all_wifi"] = allow_all
        self._write(data)
        return True

    def trust_current_wifi(self) -> bool:
        ssid = current_wifi_ssid()
        if not ssid:
            return False
        data = self._read()
        networks = {
            str(item.get("ssid", "")): bool(item.get("enabled", True))
            for item in data.get("networks", [])
            if str(item.get("ssid", "")).strip()
        }
        if networks.get(ssid) is True:
            return False
        networks[ssid] = True
        data["networks"] = [{"ssid": name, "enabled": enabled} for name, enabled in sorted(networks.items())]
        self._write(data)
        return True

    def set_network_enabled(self, ssid: str, enabled: bool) -> bool:
        data = self._read()
        changed = False
        networks: list[dict[str, object]] = []
        for item in data.get("networks", []):
            item_ssid = str(item.get("ssid", ""))
            item_enabled = bool(item.get("enabled", True))
            if item_ssid == ssid and item_enabled != enabled:
                changed = True
                item_enabled = enabled
            networks.append({"ssid": item_ssid, "enabled": item_enabled})
        data["networks"] = networks
        if not changed:
            return False
        self._write(data)
        return True

    def is_current_wifi_allowed(self) -> bool:
        policy = self.load()
        if policy.allow_all_wifi:
            return True
        return any(network.enabled and network.ssid == policy.current_ssid for network in policy.networks)

    def _read(self) -> dict[str, object]:
        if not SAFE_WIFI_POLICY_PATH.exists():
            return {"allow_all_wifi": False, "networks": []}
        enforce_private_file(SAFE_WIFI_POLICY_PATH)
        return json.loads(SAFE_WIFI_POLICY_PATH.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, object]) -> None:
        atomic_write_private(SAFE_WIFI_POLICY_PATH, json.dumps(data, indent=2, sort_keys=True) + "\n")


def current_wifi_ssid() -> str:
    """Return the active desktop Wi-Fi SSID using normal user commands only."""

    for command in (("iwgetid", "-r"), ("nmcli", "-t", "-f", "active,ssid", "dev", "wifi")):
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode != 0:
            continue
        if command[0] == "iwgetid":
            ssid = completed.stdout.strip()
            if ssid:
                return ssid
        else:
            for line in completed.stdout.splitlines():
                active, _, ssid = line.partition(":")
                if active == "yes" and ssid:
                    return ssid.replace("\\:", ":")
    return ""
