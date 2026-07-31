from __future__ import annotations

import importlib.util
import os
import re
import shlex
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SERVICE_PORT = 37891


@dataclass(frozen=True, slots=True)
class FixCommand:
    """A terminal command that can fix one failed compatibility check."""

    command: str
    requires_sudo: bool = False
    label: str = "All distros"


@dataclass(frozen=True, slots=True)
class CompatibilityCheck:
    """One startup prerequisite check and the commands needed when it fails."""

    check_id: str
    title: str
    ok: bool
    critical: bool
    explanation: str
    detail: str = ""
    fix_commands: tuple[FixCommand, ...] = field(default_factory=tuple)

    @property
    def can_skip(self) -> bool:
        return not self.critical


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """A complete desktop startup compatibility report."""

    checks: tuple[CompatibilityCheck, ...]
    service_port: int = DEFAULT_SERVICE_PORT

    @property
    def failed_checks(self) -> tuple[CompatibilityCheck, ...]:
        return tuple(check for check in self.checks if not check.ok)

    @property
    def failed_critical_checks(self) -> tuple[CompatibilityCheck, ...]:
        return tuple(check for check in self.failed_checks if check.critical)

    @property
    def failed_noncritical_checks(self) -> tuple[CompatibilityCheck, ...]:
        return tuple(check for check in self.failed_checks if not check.critical)

    @property
    def all_passed(self) -> bool:
        return not self.failed_checks

    @property
    def can_proceed_without_skip(self) -> bool:
        return not self.failed_critical_checks and not self.failed_noncritical_checks

    @property
    def can_skip_noncritical(self) -> bool:
        return not self.failed_critical_checks and bool(self.failed_noncritical_checks)


def run_compatibility_checks(service_port: int = DEFAULT_SERVICE_PORT) -> CompatibilityReport:
    """Run host checks without mutating the system."""

    checks = (
        _python_package_check("pyqt6", "PyQt6", "PyQt6 desktop UI runtime", critical=True),
        _python_package_check("zeroconf", "zeroconf", "Python mDNS fallback", critical=True),
        _binary_check("adb", "Android Debug Bridge", "adb", "USB and LAN mirroring need Android platform-tools.", critical=False),
        _binary_check("scrcpy", "scrcpy", "scrcpy", "Screen mirroring uses scrcpy for both USB and LAN.", critical=False),
        _virtual_camera_check(),
        _notification_check(),
        _audio_check(),
        _input_control_check(),
        _port_available_check(service_port),
        _firewall_check(service_port),
    )
    return CompatibilityReport(checks=checks, service_port=service_port)


def detect_distro_family() -> str:
    """Return arch, debian, fedora, or unknown based on os-release."""

    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return "unknown"
    text = os_release.read_text(encoding="utf-8", errors="replace").lower()
    ids = set(re.findall(r"^(?:id|id_like)=(.+)$", text, flags=re.MULTILINE))
    joined = " ".join(ids).replace('"', "")
    if "arch" in joined or "endeavouros" in joined or "manjaro" in joined:
        return "arch"
    if "debian" in joined or "ubuntu" in joined:
        return "debian"
    if "fedora" in joined or "rhel" in joined:
        return "fedora"
    return "unknown"


def _python_package_check(check_id: str, import_name: str, title: str, *, critical: bool) -> CompatibilityCheck:
    ok = importlib.util.find_spec(import_name) is not None
    commands = (
        FixCommand("python -m pip install -r desktop/requirements.txt -r desktop/requirements-ui.txt"),
    )
    return CompatibilityCheck(
        check_id=check_id,
        title=title,
        ok=ok,
        critical=critical,
        explanation=f"Install the Python dependency `{import_name}` into the Linkable desktop virtualenv.",
        detail="available" if ok else f"Python cannot import {import_name}.",
        fix_commands=() if ok else commands,
    )


def _binary_check(check_id: str, title: str, binary: str, explanation: str, *, critical: bool) -> CompatibilityCheck:
    path = shutil.which(binary)
    return CompatibilityCheck(
        check_id=check_id,
        title=title,
        ok=path is not None,
        critical=critical,
        explanation=explanation,
        detail=path or f"`{binary}` was not found in PATH.",
        fix_commands=() if path else _install_commands_for_binary(binary),
    )


def _install_commands_for_binary(binary: str) -> tuple[FixCommand, ...]:
    packages = {
        "adb": ("android-tools", "android-tools-adb", "android-tools"),
        "scrcpy": ("scrcpy", "scrcpy", "scrcpy"),
        "notify-send": ("libnotify", "libnotify-bin", "libnotify"),
        "ydotool": ("ydotool", "ydotool", "ydotool"),
    }
    arch_pkg, deb_pkg, fedora_pkg = packages.get(binary, (binary, binary, binary))
    return (
        FixCommand(f"sudo pacman -S --needed {arch_pkg}", requires_sudo=True, label="Arch / EndeavourOS"),
        FixCommand(f"sudo apt install {deb_pkg}", requires_sudo=True, label="Debian / Ubuntu"),
        FixCommand(f"sudo dnf install {fedora_pkg}", requires_sudo=True, label="Fedora"),
    )


def _notification_check() -> CompatibilityCheck:
    binary = shutil.which("notify-send")
    has_session_bus = bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))
    ok = binary is not None and has_session_bus
    commands: list[FixCommand] = []
    if binary is None:
        commands.extend(_install_commands_for_binary("notify-send"))
    if not has_session_bus:
        commands.append(
            FixCommand(
                "systemctl --user import-environment DBUS_SESSION_BUS_ADDRESS DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP"
            )
        )
    return CompatibilityCheck(
        check_id="desktop_notifications",
        title="Desktop notification bridge",
        ok=ok,
        critical=False,
        explanation="Linkable uses the Linux desktop notification bus for mirrored phone notifications.",
        detail="notify-send and session DBus are available" if ok else "notification command or session DBus is missing.",
        fix_commands=tuple(commands),
    )


def _audio_check() -> CompatibilityCheck:
    backend = shutil.which("pactl") or shutil.which("wpctl")
    ok = backend is not None
    return CompatibilityCheck(
        check_id="audio_controls",
        title="PipeWire/PulseAudio controls",
        ok=ok,
        critical=False,
        explanation="Call audio sliders need pactl or wpctl. PipeWire with pipewire-pulse is preferred.",
        detail=backend or "No pactl/wpctl command found.",
        fix_commands=()
        if ok
        else (
            FixCommand("sudo pacman -S --needed pipewire pipewire-pulse wireplumber", True, "Arch / EndeavourOS"),
            FixCommand("sudo apt install pipewire pipewire-pulse wireplumber pulseaudio-utils", True, "Debian / Ubuntu"),
            FixCommand("sudo dnf install pipewire pipewire-pulseaudio wireplumber pulseaudio-utils", True, "Fedora"),
        ),
    )


def _virtual_camera_check() -> CompatibilityCheck:
    v4l2_ctl = shutil.which("v4l2-ctl")
    ffmpeg = shutil.which("ffmpeg")
    modinfo = shutil.which("modinfo")
    module_available = False
    if modinfo is not None:
        module_available = _run_read_only((modinfo, "v4l2loopback")).returncode == 0
    camera_loaded = _linkable_camera_loaded() if v4l2_ctl is not None else False
    ok = v4l2_ctl is not None and ffmpeg is not None and module_available and camera_loaded

    commands: list[FixCommand] = []
    if v4l2_ctl is None or ffmpeg is None or not module_available:
        commands.extend(
            (
                FixCommand(
                    "sudo pacman -S --needed v4l2loopback-dkms v4l-utils ffmpeg",
                    True,
                    "Arch / EndeavourOS",
                ),
                FixCommand(
                    "sudo apt install v4l2loopback-dkms v4l-utils ffmpeg",
                    True,
                    "Debian / Ubuntu",
                ),
                FixCommand(
                    "sudo dnf install v4l2loopback v4l-utils ffmpeg",
                    True,
                    "Fedora",
                ),
            )
        )
    commands.append(FixCommand(_linkable_camera_setup_command(), True, "Recommended"))

    missing: list[str] = []
    if v4l2_ctl is None:
        missing.append("v4l2-ctl")
    if ffmpeg is None:
        missing.append("ffmpeg")
    if not module_available:
        missing.append("v4l2loopback kernel module")
    if not camera_loaded:
        missing.append("loaded Linkable Camera device")
    detail = "Linkable Camera is loaded." if ok else f"Missing: {', '.join(missing)}."
    return CompatibilityCheck(
        check_id="linkable_virtual_camera",
        title="Linkable virtual camera",
        ok=ok,
        critical=False,
        explanation=(
            "Camera sharing needs a V4L2 loopback device named Linkable Camera. "
            "This requires one sudo setup step and should be persisted across reboot."
        ),
        detail=detail,
        fix_commands=() if ok else tuple(commands),
    )


def _linkable_camera_loaded() -> bool:
    result = _run_read_only(("v4l2-ctl", "--list-devices"))
    output = _combined_output(result)
    return result.returncode == 0 and "Linkable Camera" in output and "/dev/video" in output


def _linkable_camera_setup_command() -> str:
    root = Path(__file__).resolve().parents[4]
    script = root / "scripts" / "setup_linkable_camera.sh"
    if script.exists():
        return f"cd {shlex.quote(str(root))} && ./scripts/setup_linkable_camera.sh --persist"
    return "sudo modprobe v4l2loopback video_nr=10 card_label='Linkable Camera' exclusive_caps=1"


def _input_control_check() -> CompatibilityCheck:
    binary = shutil.which("ydotool")
    daemon_active = _ydotool_daemon_active() if binary else False
    ok = binary is not None and daemon_active
    commands: list[FixCommand] = []
    if binary is None:
        commands.extend(_install_commands_for_binary("ydotool"))
    commands.append(FixCommand("systemctl --user enable --now ydotoold.service", False, "ydotool daemon"))
    commands.append(FixCommand("sudo systemctl enable --now ydotoold.service", True, "system ydotool daemon"))
    detail = (
        f"{binary}; ydotoold is active"
        if ok
        else (
            "`ydotool` was not found in PATH."
            if binary is None
            else f"{binary}; ydotoold is not active, so phone keyboard/trackpad events will fail."
        )
    )
    return CompatibilityCheck(
        check_id="desktop_input",
        title="Phone keyboard and trackpad backend",
        ok=ok,
        critical=False,
        explanation="PC Control uses ydotool plus ydotoold to inject keyboard, mouse, click, and scroll events.",
        detail=detail,
        fix_commands=() if ok else tuple(commands),
    )


def _ydotool_daemon_active() -> bool:
    commands = (
        ("systemctl", "--user", "is-active", "--quiet", "ydotoold.service"),
        ("pgrep", "-x", "ydotoold"),
    )
    for command in commands:
        if shutil.which(command[0]) is None:
            continue
        try:
            completed = subprocess.run(command, capture_output=True, timeout=3, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if completed.returncode == 0:
            return True
    return False


def _port_available_check(port: int) -> CompatibilityCheck:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))
    except OSError as exc:
        return CompatibilityCheck(
            check_id="listener_port",
            title=f"Linkable TCP port {port}",
            ok=False,
            critical=True,
            explanation="The desktop listener needs this TCP port for trusted phones.",
            detail=f"Port {port} is not available: {exc}",
            fix_commands=(FixCommand(f"lsof -nP -iTCP:{port} -sTCP:LISTEN"),),
        )
    return CompatibilityCheck(
        check_id="listener_port",
        title=f"Linkable TCP port {port}",
        ok=True,
        critical=True,
        explanation="The desktop listener can bind to the Linkable control port.",
        detail="available",
    )


def _firewall_check(port: int) -> CompatibilityCheck:
    firewall_tool = next((tool for tool in ("firewall-cmd", "ufw", "nft", "iptables") if shutil.which(tool)), "")
    if firewall_tool:
        return CompatibilityCheck(
            check_id="firewall",
            title="Firewall ingress rules",
            ok=True,
            critical=False,
            explanation=(
                "Firewall ingress is intentionally not probed at GUI startup because several Linux desktops route "
                "firewall-cmd/ufw queries through PolicyKit and show a sudo password popup. Linkable can still run; "
                "if discovery fails, open the Linkable TCP port and mDNS manually."
            ),
            detail=f"{firewall_tool} detected; automatic startup probing is disabled. Manual ports: TCP {port}, UDP 5353.",
            fix_commands=(
                FixCommand(
                    f"sudo firewall-cmd --add-port={port}/tcp --permanent && "
                    "sudo firewall-cmd --add-service=mdns --permanent && "
                    "sudo firewall-cmd --reload",
                    True,
                    "firewalld",
                ),
                FixCommand(f"sudo ufw allow {port}/tcp && sudo ufw allow 5353/udp", True, "ufw"),
                FixCommand(f"sudo iptables -A INPUT -p tcp --dport {port} -j ACCEPT", True, "iptables TCP"),
                FixCommand("sudo iptables -A INPUT -p udp --dport 5353 -j ACCEPT", True, "iptables mDNS"),
            ),
        )
    return CompatibilityCheck(
        check_id="firewall",
        title="Firewall ingress rules",
        ok=True,
        critical=False,
        explanation="No supported firewall command was detected, so Linkable cannot find a blocking firewall.",
        detail="no firewalld, ufw, nft, or iptables command detected",
    )


def _run_read_only(command: tuple[str, ...], timeout: float = 3.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(command, returncode=1, stdout="", stderr=str(exc))


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return " ".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
