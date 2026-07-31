from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


DEFAULT_ADB_TCP_PORT = 5555
IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
IPV4_RE = rf"{IPV4_OCTET}(?:\.{IPV4_OCTET}){{3}}"


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def compact_output(self) -> str:
        output = "\n".join(part for part in (self.stdout.strip(), self.stderr.strip()) if part)
        return output or f"exit={self.returncode}"


@dataclass(frozen=True)
class AdbDevice:
    serial: str
    state: str
    detail: str = ""

    @property
    def is_tcp(self) -> bool:
        return re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}:\d+", self.serial) is not None

    @property
    def is_ready(self) -> bool:
        return self.state == "device"


@dataclass(frozen=True)
class ScrcpyStatus:
    adb_path: str = ""
    scrcpy_path: str = ""
    devices: tuple[AdbDevice, ...] = ()

    @property
    def adb_available(self) -> bool:
        return bool(self.adb_path)

    @property
    def scrcpy_available(self) -> bool:
        return bool(self.scrcpy_path)

    @property
    def ready(self) -> bool:
        return self.adb_available and self.scrcpy_available

    def format(self) -> str:
        lines = [
            "Screen mirroring status",
            f"adb: {self.adb_path or 'not found'}",
            f"scrcpy: {self.scrcpy_path or 'not found'}",
        ]
        if self.devices:
            lines.append("ADB devices:")
            lines.extend(f"- {device.serial} state={device.state} {device.detail}".rstrip() for device in self.devices)
        else:
            lines.append("ADB devices: none")
        if not self.scrcpy_available:
            lines.append("note: install scrcpy to use phone screen mirroring.")
        if not self.adb_available:
            lines.append("note: install Android platform-tools or source scripts/android_env.sh.")
        lines.append("note: USB mirroring needs USB debugging authorization. LAN mirroring needs ADB TCP/IP or Android Wireless debugging.")
        return "\n".join(lines)


@dataclass(frozen=True)
class MirrorLaunch:
    result: CommandResult
    process: subprocess.Popen[str] | None = None


class ScrcpyManager:
    def __init__(self, *, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(__file__).resolve().parents[4]
        self._lock = Lock()
        self._processes: list[subprocess.Popen[str]] = []

    def status(self) -> ScrcpyStatus:
        adb_path = self.adb_path()
        devices: tuple[AdbDevice, ...] = ()
        if adb_path:
            devices = tuple(self.adb_devices())
        return ScrcpyStatus(
            adb_path=adb_path,
            scrcpy_path=self.scrcpy_path(),
            devices=devices,
        )

    def adb_path(self) -> str:
        candidates = [
            os.environ.get("LINKABLE_ADB_BIN", ""),
            os.environ.get("ADB", ""),
            shutil.which("adb") or "",
        ]
        for env_name in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
            root = os.environ.get(env_name, "")
            if root:
                candidates.append(str(Path(root) / "platform-tools" / "adb"))
        candidates.append(str(Path.home() / "Android" / "Sdk" / "platform-tools" / "adb"))
        return first_executable(candidates)

    def scrcpy_path(self) -> str:
        return first_executable(
            [
                os.environ.get("LINKABLE_SCRCPY_BIN", ""),
                shutil.which("scrcpy") or "",
            ]
        )

    def adb_devices(self) -> list[AdbDevice]:
        adb = self.adb_path()
        if not adb:
            return []
        result = run_command((adb, "devices", "-l"), timeout=8)
        if not result.ok:
            return []
        return parse_adb_devices(result.stdout)

    def first_usb_device(self) -> AdbDevice | None:
        return next((device for device in self.adb_devices() if device.is_ready and not device.is_tcp), None)

    def tcp_serial(self, host: str, *, port: int = DEFAULT_ADB_TCP_PORT) -> str:
        host = normalize_adb_target(host)
        if not host:
            return ""
        if ":" in host:
            return host
        return f"{host}:{port}"

    def enable_adb_tcpip(self, *, port: int = DEFAULT_ADB_TCP_PORT) -> CommandResult:
        adb = self.adb_path()
        if not adb:
            return CommandResult(command=("adb", "tcpip", str(port)), returncode=1, stderr="adb not found")
        return run_command((adb, "tcpip", str(port)), timeout=12)

    def connect_lan_adb(self, host: str, *, port: int = DEFAULT_ADB_TCP_PORT) -> CommandResult:
        adb = self.adb_path()
        if not adb:
            return CommandResult(command=("adb", "connect", self.tcp_serial(host, port=port)), returncode=1, stderr="adb not found")
        serial = self.tcp_serial(host, port=port)
        if not serial:
            return CommandResult(command=(adb, "connect", "<phone-ip>"), returncode=1, stderr="phone LAN IP is required")
        return run_command((adb, "connect", serial), timeout=12)

    def disconnect_lan_adb(self, host: str, *, port: int = DEFAULT_ADB_TCP_PORT) -> CommandResult:
        adb = self.adb_path()
        serial = self.tcp_serial(host, port=port)
        if not adb:
            return CommandResult(command=("adb", "disconnect", serial), returncode=1, stderr="adb not found")
        return run_command((adb, "disconnect", serial), timeout=8)

    def launch_usb_mirror(self) -> MirrorLaunch:
        device = self.first_usb_device()
        if device is None:
            return MirrorLaunch(
                result=CommandResult(
                    command=("scrcpy", "--serial", "<usb-device>"),
                    returncode=1,
                    stderr="No authorized USB ADB device found. Enable USB debugging and accept the phone authorization prompt.",
                )
            )
        return self.launch_mirror(device.serial)

    def launch_lan_mirror(self, host: str, *, port: int = DEFAULT_ADB_TCP_PORT) -> MirrorLaunch:
        serial = self.tcp_serial(host, port=port)
        if not serial:
            return MirrorLaunch(
                result=CommandResult(command=("scrcpy", "--serial", "<phone-ip>"), returncode=1, stderr="phone LAN IP is required")
            )
        connect = self._connect_lan_adb_with_retries(host, port=port)
        output = connect.compact_output().lower()
        if not connect.ok and "already connected" not in output and "connected to" not in output:
            return MirrorLaunch(result=connect)
        return self.launch_mirror(serial)

    def _connect_lan_adb_with_retries(
        self,
        host: str,
        *,
        port: int = DEFAULT_ADB_TCP_PORT,
        attempts: int = 3,
        delay_seconds: float = 0.8,
    ) -> CommandResult:
        result = self.connect_lan_adb(host, port=port)
        for _ in range(max(0, attempts - 1)):
            output = result.compact_output().lower()
            if result.ok or "already connected" in output or "connected to" in output:
                return result
            time.sleep(delay_seconds)
            result = self.connect_lan_adb(host, port=port)
        return result

    def launch_mirror(self, serial: str) -> MirrorLaunch:
        scrcpy = self.scrcpy_path()
        if not scrcpy:
            return MirrorLaunch(result=CommandResult(command=("scrcpy",), returncode=1, stderr="scrcpy not found"))
        command = (
            scrcpy,
            "--serial",
            serial,
            "--no-audio",
            "--stay-awake",
            "--window-title",
            f"Linkable Mirror - {serial}",
        )
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError as exc:
            return MirrorLaunch(result=CommandResult(command=command, returncode=1, stderr=str(exc)))
        time.sleep(0.45)
        returncode = process.poll()
        if returncode is not None:
            return MirrorLaunch(
                result=CommandResult(
                    command=command,
                    returncode=returncode,
                    stderr=(
                        f"scrcpy exited immediately for {serial}. "
                        "Refresh mirror status and confirm this serial is authorized in `adb devices -l`."
                    ),
                )
            )
        self._track_process(process)
        return MirrorLaunch(
            result=CommandResult(
                command=command,
                returncode=0,
                stdout=f"Started scrcpy for {serial} with pid {process.pid}. Locked phones can be unlocked from the scrcpy window after ADB authorization.",
            ),
            process=process,
        )

    def stop_all(self) -> None:
        """Terminate mirror processes launched by this app instance."""

        with self._lock:
            processes = [process for process in self._processes if process.poll() is None]
            self._processes = []
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.5)

    def _track_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._processes = [existing for existing in self._processes if existing.poll() is None]
            self._processes.append(process)


def first_executable(candidates: list[str]) -> str:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return ""


def run_command(command: tuple[str, ...], *, timeout: int = 8) -> CommandResult:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(command=command, returncode=1, stderr=str(exc))
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def extract_ipv4_host(text: str) -> str:
    match = re.search(rf"\b({IPV4_RE})\b", text)
    return match.group(1) if match is not None else ""


def normalize_adb_target(value: str) -> str:
    text = value.strip().strip("[](){}<>")
    if not text:
        return ""
    if " at " in text:
        return extract_ipv4_host(text)

    token = text.split(maxsplit=1)[0].strip(".,;")
    ipv4 = re.fullmatch(rf"({IPV4_RE})(?::(\d{{1,5}}))?", token)
    if ipv4 is not None:
        return token

    embedded_ipv4 = re.search(rf"\b({IPV4_RE})(?::\d{{1,5}})?\b", text)
    if embedded_ipv4 is not None:
        return embedded_ipv4.group(0)

    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.-]*(?::\d{1,5})?", token):
        return token
    return ""


def parse_adb_devices(text: str) -> list[AdbDevice]:
    devices: list[AdbDevice] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices"):
            continue
        parts = line.split(maxsplit=2)
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        detail = parts[2] if len(parts) > 2 else ""
        devices.append(AdbDevice(serial=serial, state=state, detail=detail))
    return devices
