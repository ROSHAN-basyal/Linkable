from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from linkable_desktop.config import CONFIG_DIR
from linkable_desktop.secure_storage import atomic_write_private, enforce_private_file


SETUP_STATE_PATH = CONFIG_DIR / "desktop_setup.json"
SAFE_NETWORKS_PATH = CONFIG_DIR / "safe_networks.json"


@dataclass(frozen=True, slots=True)
class FirstRunState:
    """Persisted state indicating whether the desktop first-run wizard finished."""

    completed: bool
    safe_wifi_ssids: tuple[str, ...]
    skipped_optional_checks: tuple[str, ...] = ()


def load_first_run_state() -> FirstRunState:
    if not SETUP_STATE_PATH.exists():
        return FirstRunState(completed=False, safe_wifi_ssids=())
    enforce_private_file(SETUP_STATE_PATH)
    data = json.loads(SETUP_STATE_PATH.read_text(encoding="utf-8"))
    return FirstRunState(
        completed=bool(data.get("completed", False)),
        safe_wifi_ssids=tuple(str(item) for item in data.get("safe_wifi_ssids", [])),
        skipped_optional_checks=tuple(str(item) for item in data.get("skipped_optional_checks", [])),
    )


def save_first_run_state(state: FirstRunState) -> None:
    atomic_write_private(
        SETUP_STATE_PATH,
        json.dumps(
            {
                "completed": state.completed,
                "safe_wifi_ssids": list(state.safe_wifi_ssids),
                "skipped_optional_checks": list(state.skipped_optional_checks),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def add_safe_wifi_ssid(ssid: str) -> tuple[str, ...]:
    current = set(load_first_run_state().safe_wifi_ssids)
    if ssid:
        current.add(ssid)
    safe = tuple(sorted(current))
    current_state = load_first_run_state()
    save_first_run_state(
        FirstRunState(
            completed=True,
            safe_wifi_ssids=safe,
            skipped_optional_checks=current_state.skipped_optional_checks,
        )
    )
    atomic_write_private(SAFE_NETWORKS_PATH, json.dumps({"wifi_ssids": list(safe)}, indent=2, sort_keys=True) + "\n")
    return safe


def save_skipped_optional_checks(check_ids: tuple[str, ...]) -> None:
    """Persist optional compatibility checks the user explicitly chose to skip."""

    current = load_first_run_state()
    skipped = tuple(sorted(set(current.skipped_optional_checks).union(check_ids)))
    save_first_run_state(
        FirstRunState(
            completed=current.completed,
            safe_wifi_ssids=current.safe_wifi_ssids,
            skipped_optional_checks=skipped,
        )
    )


def current_wifi_ssid() -> str:
    """Best-effort current Wi-Fi SSID detection across common Linux setups."""

    if shutil.which("iwgetid"):
        result = _run(("iwgetid", "-r"))
        ssid = result.stdout.strip()
        if result.returncode == 0 and ssid:
            return ssid
    if shutil.which("nmcli"):
        result = _run(("nmcli", "-t", "-f", "active,ssid", "dev", "wifi"))
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                active, _, ssid = line.partition(":")
                if active == "yes" and ssid:
                    return ssid.replace("\\:", ":")
    return ""


def systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "linkable-desktop.service"


def build_systemd_unit(root_dir: Path) -> str:
    env_path = os.environ.get("PATH", "")
    return "\n".join(
        [
            "[Unit]",
            "Description=Linkable desktop companion",
            "After=graphical-session.target network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={root_dir}",
            f"Environment=PATH={env_path}",
            f"ExecStart={root_dir / 'scripts' / 'run_desktop_gui.sh'} --background-service",
            "Restart=on-failure",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )


def install_systemd_user_service(root_dir: Path) -> None:
    unit_path = systemd_unit_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(build_systemd_unit(root_dir), encoding="utf-8")
    _run(("systemctl", "--user", "daemon-reload"), timeout=6.0)
    result = _run(("systemctl", "--user", "enable", "linkable-desktop.service"), timeout=12.0)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "systemctl failed")


def _run(command: tuple[str, ...], timeout: float = 3.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr=str(exc))
