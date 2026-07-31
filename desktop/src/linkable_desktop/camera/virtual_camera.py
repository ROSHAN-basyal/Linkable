from __future__ import annotations

import base64
import os
import queue
import re
import shlex
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock, Thread


LINKABLE_CAMERA_LABEL = "Linkable Camera"
DEFAULT_VIDEO_NR = 10
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 480
DEFAULT_FPS = 12
_PLACEHOLDER_MJPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAgAAAQABAAD//gAQTGF2YzYyLjI4LjEwMQD/2wBDAAgEBAQEBAUFBQUFBQYGBgYGBgYGBgYGBgYHBwcICAgHBwcGBgcHCAgICAkJCQgICAgJCQoKCgwMCwsODg4RERT/xABLAAEBAAAAAAAAAAAAAAAAAAAACAEBAAAAAAAAAAAAAAAAAAAAABABAAAAAAAAAAAAAAAAAAAAABEBAAAAAAAAAAAAAAAAAAAAAP/AABEIAPABQAMBIgACEQADEQD/2gAMAwEAAhEDEQA/AJ/AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAB//9k="
)
_PLACEHOLDER_CACHE: dict[tuple[int, int], bytes] = {}


@dataclass(frozen=True, slots=True)
class VirtualCameraStatus:
    """Result of discovering or preparing the Linux V4L2 virtual camera."""

    ok: bool
    device: str = ""
    detail: str = ""
    fix_commands: tuple[str, ...] = ()


class VirtualCameraSink:
    """Streams received phone MJPEG frames into a V4L2 loopback camera device."""

    def __init__(
        self,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        fps: int = DEFAULT_FPS,
        on_status: Callable[[str], None] = lambda message: None,
    ) -> None:
        self.width = max(160, int(width))
        self.height = max(120, int(height))
        self.fps = max(1, min(30, int(fps)))
        self._on_status = on_status
        self._frames: queue.Queue[bytes] = queue.Queue(maxsize=2)
        self._stop = Event()
        self._lock = Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._writer: Thread | None = None
        self._device = ""
        self.frames_written = 0

    @property
    def device(self) -> str:
        return self._device

    def start(self) -> VirtualCameraStatus:
        """Prepare `Linkable Camera` and start ffmpeg as the V4L2 writer."""

        status = ensure_linkable_camera()
        if not status.ok:
            return status
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return VirtualCameraStatus(
                ok=False,
                detail="ffmpeg is required to feed Linkable Camera.",
                fix_commands=("sudo pacman -S ffmpeg", "sudo apt install ffmpeg", "sudo dnf install ffmpeg"),
            )
        self._device = status.device
        command = (
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "image2pipe",
            "-probesize",
            "32",
            "-analyzeduration",
            "0",
            "-framerate",
            str(self.fps),
            "-vcodec",
            "mjpeg",
            "-i",
            "pipe:0",
            "-vf",
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2",
            "-pix_fmt",
            "yuyv422",
            "-f",
            "v4l2",
            self._device,
        )
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            return VirtualCameraStatus(ok=False, device=self._device, detail=f"Could not start ffmpeg: {exc}")
        time.sleep(0.25)
        if process.poll() is not None:
            stderr = ""
            if process.stderr is not None:
                stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
            return VirtualCameraStatus(
                ok=False,
                device=self._device,
                detail=stderr or f"ffmpeg exited immediately with code {process.returncode}.",
            )
        with self._lock:
            self._process = process
            self._stop.clear()
            self.frames_written = 0
            self._writer = Thread(target=self._write_loop, name="linkable-virtual-camera", daemon=True)
            self._writer.start()
        self._on_status(f"Linkable Camera is active at {self._device}. Select it in your PC app.")
        return VirtualCameraStatus(ok=True, device=self._device, detail=f"Linkable Camera active at {self._device}.")

    def push_frame(self, frame: bytes) -> None:
        """Queue the newest frame and drop stale frames to keep memory bounded."""

        if not frame:
            return
        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            self._frames.put_nowait(frame)
        except queue.Full:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                pass
            try:
                self._frames.put_nowait(frame)
            except queue.Full:
                pass

    def stop(self) -> None:
        """Stop the virtual camera writer process and clear queued frame data."""

        self._stop.set()
        with self._lock:
            process = self._process
            writer = self._writer
            self._process = None
            self._writer = None
        while True:
            try:
                self._frames.get_nowait()
            except queue.Empty:
                break
        if process is not None:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.5)
        if writer is not None:
            writer.join(timeout=1.0)

    def _write_loop(self) -> None:
        frame_interval = 1.0 / float(self.fps)
        next_write_at = 0.0
        last_frame: bytes | None = None
        while not self._stop.is_set():
            now = time.monotonic()
            if now < next_write_at:
                try:
                    last_frame = self._frames.get(timeout=min(0.10, next_write_at - now))
                    last_frame = self._newest_queued_frame(last_frame)
                except queue.Empty:
                    pass
                continue

            try:
                last_frame = self._newest_queued_frame(self._frames.get_nowait())
            except queue.Empty:
                pass

            frame = last_frame or _placeholder_mjpeg(self.width, self.height)
            with self._lock:
                process = self._process
            if process is None or process.stdin is None or process.poll() is not None:
                return
            try:
                process.stdin.write(frame)
                process.stdin.flush()
                self.frames_written += 1
                next_write_at = max(next_write_at + frame_interval, time.monotonic() + frame_interval)
            except OSError as exc:
                self._on_status(f"Linkable Camera writer stopped: {exc}")
                return

    def _newest_queued_frame(self, first_frame: bytes) -> bytes:
        """Return the newest pending camera frame, dropping stale queued frames."""

        frame = first_frame
        while True:
            try:
                frame = self._frames.get_nowait()
            except queue.Empty:
                return frame


def ensure_linkable_camera() -> VirtualCameraStatus:
    """Find or create a V4L2 loopback device labeled `Linkable Camera`."""

    existing = find_linkable_camera()
    if existing:
        return VirtualCameraStatus(ok=True, device=existing, detail=f"Found Linkable Camera at {existing}.")
    if shutil.which("v4l2-ctl") is None:
        return VirtualCameraStatus(
            ok=False,
            detail="v4l2-ctl is required to discover Linux camera devices.",
            fix_commands=("sudo pacman -S v4l-utils", "sudo apt install v4l-utils", "sudo dnf install v4l-utils"),
        )
    if shutil.which("modprobe") is None:
        return VirtualCameraStatus(ok=False, detail="modprobe is required to create a v4l2loopback camera.")
    video_nr = _first_free_video_nr()
    command = _modprobe_command(video_nr)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=8)
    if completed.returncode != 0:
        output = (completed.stderr or completed.stdout or "Could not create Linkable Camera.").strip()
        if _sudo_password_required(output):
            return VirtualCameraStatus(
                ok=False,
                detail=(
                    "Linkable Camera is not loaded. The desktop GUI cannot enter your sudo password, "
                    "so the virtual camera must be set up once from a terminal."
                ),
                fix_commands=(
                    _setup_script_command(persist=True),
                    _shell_modprobe_command(video_nr),
                ),
            )
        return VirtualCameraStatus(
            ok=False,
            detail=output,
            fix_commands=(_setup_script_command(persist=True), _shell_modprobe_command(video_nr)),
        )
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        existing = find_linkable_camera()
        if existing:
            return VirtualCameraStatus(ok=True, device=existing, detail=f"Created Linkable Camera at {existing}.")
        time.sleep(0.25)
    return VirtualCameraStatus(
        ok=False,
        detail="v4l2loopback loaded but Linkable Camera did not appear.",
        fix_commands=("v4l2-ctl --list-devices",),
    )


def find_linkable_camera() -> str:
    """Return the first `/dev/video*` path whose card label is `Linkable Camera`."""

    for label, devices in _list_v4l2_devices().items():
        if LINKABLE_CAMERA_LABEL.lower() in label.lower() and devices:
            return devices[0]
    return ""


def list_v4l2_summary() -> str:
    """Return a concise V4L2 camera list for diagnostics."""

    devices = _list_v4l2_devices()
    if not devices:
        return "No V4L2 video devices detected."
    return "\n".join(f"{label}: {', '.join(paths)}" for label, paths in devices.items())


def _list_v4l2_devices() -> dict[str, list[str]]:
    v4l2_ctl = shutil.which("v4l2-ctl")
    if not v4l2_ctl:
        return {}
    completed = subprocess.run((v4l2_ctl, "--list-devices"), capture_output=True, text=True, timeout=5)
    if completed.returncode != 0:
        return {}
    devices: dict[str, list[str]] = {}
    current_label = ""
    for raw_line in completed.stdout.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if not line.startswith(("\t", " ")):
            current_label = re.sub(r"\s+$", "", line.rstrip(":"))
            devices.setdefault(current_label, [])
            continue
        path = line.strip()
        if current_label and path.startswith("/dev/video"):
            devices[current_label].append(path)
    return devices


def _first_free_video_nr() -> int:
    for candidate in (DEFAULT_VIDEO_NR, 11, 12, 13, 20, 21):
        if not Path(f"/dev/video{candidate}").exists():
            return candidate
    return DEFAULT_VIDEO_NR


def _modprobe_command(video_nr: int) -> tuple[str, ...]:
    base = (
        "modprobe",
        "v4l2loopback",
        f"video_nr={video_nr}",
        f"card_label={LINKABLE_CAMERA_LABEL}",
        "exclusive_caps=1",
    )
    if os.geteuid() == 0:
        return base
    return ("sudo", "-n", *base)


def _setup_script_command(*, persist: bool) -> str:
    root = Path(__file__).resolve().parents[4]
    script = root / "scripts" / "setup_linkable_camera.sh"
    if script.exists():
        suffix = " --persist" if persist else ""
        return f"cd {shlex.quote(str(root))} && ./scripts/setup_linkable_camera.sh{suffix}"
    return _shell_modprobe_command(DEFAULT_VIDEO_NR)


def _shell_modprobe_command(video_nr: int) -> str:
    return (
        f"sudo modprobe v4l2loopback video_nr={video_nr} "
        f"card_label='{LINKABLE_CAMERA_LABEL}' exclusive_caps=1"
    )


def _sudo_password_required(output: str) -> bool:
    lowered = output.lower()
    return "password is required" in lowered or "a password is required" in lowered


def _placeholder_mjpeg(width: int, height: int) -> bytes:
    """Return a visible MJPEG test pattern while waiting for real phone frames."""

    key = (max(160, int(width)), max(120, int(height)))
    cached = _PLACEHOLDER_CACHE.get(key)
    if cached:
        return cached
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        try:
            completed = subprocess.run(
                (
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    f"testsrc=size={key[0]}x{key[1]}:rate=1",
                    "-frames:v",
                    "1",
                    "-q:v",
                    "5",
                    "-f",
                    "mjpeg",
                    "pipe:1",
                ),
                capture_output=True,
                timeout=3,
                check=False,
            )
            if completed.returncode == 0 and completed.stdout.startswith(b"\xff\xd8"):
                _PLACEHOLDER_CACHE[key] = completed.stdout
                return completed.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    return _PLACEHOLDER_MJPEG
