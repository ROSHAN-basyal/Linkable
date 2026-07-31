from __future__ import annotations

import hashlib
import json
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path

from linkable_desktop.secure_storage import atomic_write_private, ensure_private_directory, enforce_private_file


CONFIG_DIR = Path.home() / ".config" / "linkable"
CONFIG_PATH = CONFIG_DIR / "config.json"
IDENTITY_PATH = CONFIG_DIR / "identity_key.pem"
TRUST_STORE_PATH = CONFIG_DIR / "trusted_devices.json"


@dataclass(slots=True)
class DiscoveryConfig:
    device_name: str
    device_id: str
    protocol_version: str = "1.0.0"
    service_type: str = "_linkable._tcp.local."
    service_port: int = 37891
    browse_interval_sec: float = 2.0
    max_frame_size: int = 1_048_576
    pairing_timeout_sec: float = 120.0

    def txt_record(self) -> dict[str, str]:
        return {
            "device_name": self.device_name,
            "protocol_version": self.protocol_version,
            "device_id": self.device_id,
        }


def _machine_fingerprint() -> str:
    machine_id_path = Path("/etc/machine-id")
    if machine_id_path.exists():
        source = machine_id_path.read_text(encoding="utf-8").strip()
    else:
        source = f"{platform.node()}::{platform.platform()}"
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return digest[:16]


def default_discovery_config() -> DiscoveryConfig:
    return DiscoveryConfig(
        device_name=os.environ.get("LINKABLE_DEVICE_NAME", platform.node() or "linkable-linux"),
        device_id=os.environ.get("LINKABLE_DEVICE_ID", _machine_fingerprint()),
        protocol_version=os.environ.get("LINKABLE_PROTOCOL_VERSION", "1.0.0"),
        service_type=os.environ.get("LINKABLE_SERVICE_TYPE", "_linkable._tcp.local."),
        service_port=int(os.environ.get("LINKABLE_SERVICE_PORT", "37891")),
    )


def load_discovery_config(path: Path | None = None) -> DiscoveryConfig:
    config = default_discovery_config()
    file_path = path or CONFIG_PATH
    if not file_path.exists():
        return config

    enforce_private_file(file_path)
    data = json.loads(file_path.read_text(encoding="utf-8"))
    merged = asdict(config)
    for key, value in data.items():
        if key in merged:
            merged[key] = value
    return DiscoveryConfig(**merged)


def save_default_config_if_missing(path: Path | None = None) -> Path:
    file_path = path or CONFIG_PATH
    if file_path.exists():
        enforce_private_file(file_path)
        return file_path
    atomic_write_private(
        file_path,
        json.dumps(asdict(default_discovery_config()), indent=2, sort_keys=True) + "\n",
    )
    return file_path


def ensure_state_dir() -> Path:
    return ensure_private_directory(CONFIG_DIR)
