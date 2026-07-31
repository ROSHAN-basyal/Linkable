from __future__ import annotations

import ipaddress
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from types import SimpleNamespace
from threading import Lock
from typing import Any

from linkable_desktop.config import DiscoveryConfig

def _load_zeroconf() -> tuple[type[Exception], Any, Any]:
    try:
        from zeroconf import NonUniqueNameException, ServiceInfo, Zeroconf
    except ImportError as exc:  # pragma: no cover - exercised in runtime environments without dependency
        raise RuntimeError(
            "zeroconf is not installed. Install desktop requirements before using mDNS advertisement."
        ) from exc
    return NonUniqueNameException, ServiceInfo, Zeroconf


def _preferred_ipv4_address() -> str | None:
    override = os.environ.get("LINKABLE_SERVICE_IP", "").strip()
    if override:
        try:
            candidate = ipaddress.ip_address(override)
        except ValueError:
            return None
        if isinstance(candidate, ipaddress.IPv4Address) and not candidate.is_loopback:
            return override
        return None

    for target in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect((target, 80))
                address = sock.getsockname()[0]
        except OSError:
            continue
        if address and not address.startswith("127."):
            return address
    return None


def _hostname_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    hostname = socket.gethostname()
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET)
    except OSError:
        infos = []
    for family, _, _, _, sockaddr in infos:
        if family != socket.AF_INET or not sockaddr:
            continue
        ip = sockaddr[0]
        if ip.startswith("127."):
            continue
        addresses.add(ip)
    return sorted(addresses)


def _discover_ipv4_addresses() -> list[bytes]:
    preferred = _preferred_ipv4_address()
    ordered: list[str] = []
    if preferred is not None:
        ordered.append(preferred)
    for address in _hostname_ipv4_addresses():
        if address != preferred:
            ordered.append(address)
    if not ordered:
        ordered.append("127.0.0.1")
    # Zeroconf + Android service resolution is more reliable when the primary LAN
    # address is advertised first. Avoid bridge/tunnel interfaces winning by sort order.
    deduped = list(dict.fromkeys(ordered))
    if preferred is not None:
        return [ipaddress.ip_address(preferred).packed]
    return [ipaddress.ip_address(ip).packed for ip in deduped]


def _service_name(config: DiscoveryConfig) -> str:
    suffix = config.service_type
    if not suffix.endswith("."):
        suffix += "."
    return f"{config.device_name}.{suffix}"


def _txt_record(config: DiscoveryConfig) -> dict[str, str]:
    record = config.txt_record()
    preferred = _preferred_ipv4_address()
    if preferred is not None:
        record["host"] = preferred
    record["port"] = str(config.service_port)
    return record


@dataclass(slots=True)
class DiscoveryAdvertisement:
    config: DiscoveryConfig
    zeroconf: Any | None = None
    info: Any | None = None
    _avahi_process: subprocess.Popen[bytes] | None = None
    _lock: Lock = field(default_factory=Lock)

    def build_service_info(self) -> Any:
        _, ServiceInfo, _ = _load_zeroconf()
        return ServiceInfo(
            type_=self.config.service_type,
            name=_service_name(self.config),
            addresses=_discover_ipv4_addresses(),
            port=self.config.service_port,
            properties={
                key.encode("utf-8"): value.encode("utf-8")
                for key, value in _txt_record(self.config).items()
            },
            server=f"{socket.gethostname()}.local.",
        )

    def start(self) -> None:
        with self._lock:
            if self.zeroconf is not None or self._avahi_process is not None:
                return
            if self._should_use_avahi():
                self._start_avahi()
                return
            NonUniqueNameException, _, Zeroconf = _load_zeroconf()
            # Passing explicit interface lists currently crashes zeroconf on
            # this Python 3.14 environment. Keep the stable default socket
            # setup, but advertise only the selected LAN address in ServiceInfo.
            self.zeroconf = Zeroconf()
            self.info = self.build_service_info()
            try:
                self.zeroconf.register_service(self.info)
            except NonUniqueNameException as exc:  # pragma: no cover - environment-dependent
                self.stop()
                raise RuntimeError(f"service name already in use: {self.info.name}") from exc

    def stop(self) -> None:
        with self._lock:
            if self._avahi_process is not None:
                self._avahi_process.terminate()
                try:
                    self._avahi_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._avahi_process.kill()
                    self._avahi_process.wait(timeout=2)
                self._avahi_process = None
                self.info = None
                return
            if self.zeroconf is None:
                return
            if self.info is not None:
                try:
                    self.zeroconf.unregister_service(self.info)
                except Exception:
                    pass
            self.zeroconf.close()
            self.zeroconf = None
            self.info = None

    def backend_name(self) -> str:
        if self._avahi_process is not None:
            return "avahi"
        if self.zeroconf is not None:
            return "zeroconf"
        return "stopped"

    def _should_use_avahi(self) -> bool:
        backend = os.environ.get("LINKABLE_MDNS_BACKEND", "auto").strip().lower()
        if backend == "zeroconf":
            return False
        if backend == "avahi":
            return True
        return shutil.which("avahi-publish-service") is not None

    def _start_avahi(self) -> None:
        executable = shutil.which("avahi-publish-service")
        if executable is None:
            raise RuntimeError("avahi-publish-service is not installed")
        service_type = self.config.service_type
        if service_type.endswith(".local."):
            service_type = service_type.removesuffix(".local.")
        service_type = service_type.rstrip(".")
        txt_args = [f"{key}={value}" for key, value in _txt_record(self.config).items()]
        command = [
            executable,
            "--service",
            self.config.device_name,
            service_type,
            str(self.config.service_port),
            *txt_args,
        ]
        self._avahi_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        try:
            return_code = self._avahi_process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            self.info = SimpleNamespace(addresses=_discover_ipv4_addresses())
            return
        stderr = self._avahi_process.stderr.read().decode("utf-8", errors="replace") if self._avahi_process.stderr else ""
        self._avahi_process = None
        raise RuntimeError(f"avahi-publish-service exited early with {return_code}: {stderr.strip()}")
