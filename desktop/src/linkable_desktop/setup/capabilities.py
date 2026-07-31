from __future__ import annotations

import shutil
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityCheck:
    name: str
    ok: bool
    detail: str
    command: str = ""
    sudo: bool = False


def run_compatibility_checks(service_port: int = 37891) -> list[CapabilityCheck]:
    """Return actionable desktop requirements without mutating the host."""

    checks = [
        _command_check("Python virtualenv", "python", "Desktop runtime Python is available."),
        _command_check("Desktop notifications", "notify-send", "Install libnotify for Linux notification mirroring."),
        _command_check("mDNS advertisement", "avahi-publish-service", "Install avahi for reliable cross-distro LAN discovery."),
        _command_check("ADB", "adb", "Install Android platform-tools for USB/LAN mirroring."),
        _command_check("scrcpy", "scrcpy", "Install scrcpy for phone screen mirroring."),
        _command_check("Input control", "ydotool", "Install ydotool and run ydotoold for Wayland/X11 input injection."),
        _audio_backend_check(),
        _port_check(service_port),
    ]
    return checks


def setup_commands(service_port: int = 37891) -> list[CapabilityCheck]:
    """Commands shown in the first-run wizard; callers decide what to run."""

    return [
        CapabilityCheck(
            name="Firewalld allow Linkable TCP control",
            ok=False,
            detail=f"Allows paired phones to reach the encrypted Linkable listener on TCP {service_port}.",
            command=f"sudo firewall-cmd --add-port={service_port}/tcp --permanent && sudo firewall-cmd --reload",
            sudo=True,
        ),
        CapabilityCheck(
            name="Firewalld allow mDNS",
            ok=False,
            detail="Allows Android NSD/mDNS discovery to find this desktop on trusted LANs.",
            command="sudo firewall-cmd --add-service=mdns --permanent && sudo firewall-cmd --reload",
            sudo=True,
        ),
        CapabilityCheck(
            name="Start Linkable background service on login",
            ok=False,
            detail="Installs the launcher and enables only the background LAN service on login; the GUI remains manual.",
            command="./scripts/install_desktop_app.sh --autostart",
        ),
        CapabilityCheck(
            name="Enable ydotool daemon",
            ok=False,
            detail="ydotool needs the uinput daemon for keyboard/trackpad injection.",
            command="systemctl --user enable --now ydotoold.service",
        ),
    ]


def format_checks(checks: list[CapabilityCheck]) -> str:
    lines: list[str] = []
    for check in checks:
        marker = "OK" if check.ok else "MISSING"
        lines.append(f"[{marker}] {check.name}: {check.detail}")
        if check.command:
            prefix = "sudo command" if check.sudo else "command"
            lines.append(f"  {prefix}: {check.command}")
    return "\n".join(lines)


def _command_check(name: str, executable: str, missing_detail: str) -> CapabilityCheck:
    path = shutil.which(executable)
    return CapabilityCheck(
        name=name,
        ok=bool(path),
        detail=path or missing_detail,
    )


def _audio_backend_check() -> CapabilityCheck:
    backend = shutil.which("wpctl") or shutil.which("pactl")
    return CapabilityCheck(
        name="Audio controls",
        ok=bool(backend),
        detail=backend or "Install PipeWire wpctl or PulseAudio pactl for volume/mic controls.",
    )


def _port_check(port: int) -> CapabilityCheck:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            result = sock.connect_ex(("127.0.0.1", port))
    except OSError as exc:
        return CapabilityCheck(
            name=f"TCP port {port}",
            ok=False,
            detail=f"could not check port availability: {exc}",
        )
    return CapabilityCheck(
        name=f"TCP port {port}",
        ok=result != 0,
        detail="available" if result != 0 else "already in use; close the other Linkable listener first.",
    )
