from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Thread


@dataclass(frozen=True, slots=True)
class PreviewFrame:
    """One RGB frame read back from the PC-facing V4L2 camera device."""

    rgb: bytes
    width: int
    height: int


class V4L2PreviewReader:
    """Reads frames from Linkable Camera to verify what PC apps actually receive."""

    def __init__(
        self,
        *,
        device: str,
        width: int,
        height: int,
        fps: int,
        on_frame: Callable[[PreviewFrame], None],
        on_status: Callable[[str], None],
    ) -> None:
        self.device = device
        self.width = max(160, int(width))
        self.height = max(120, int(height))
        self.fps = max(1, min(30, int(fps)))
        self._on_frame = on_frame
        self._on_status = on_status
        self._stop = Event()
        self._thread: Thread | None = None
        self._process: subprocess.Popen[bytes] | None = None

    def start(self) -> bool:
        """Start reading from the V4L2 camera with ffmpeg."""

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self._on_status("ffmpeg is required for Camera test preview.")
            return False
        if self._thread is not None:
            return True
        command = (
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "v4l2",
            "-framerate",
            str(self.fps),
            "-video_size",
            f"{self.width}x{self.height}",
            "-i",
            self.device,
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        )
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._on_status(f"Could not start Camera test preview: {exc}")
            return False
        self._thread = Thread(target=self._read_loop, name="linkable-camera-preview", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop the preview reader and release the V4L2 capture handle."""

        self._stop.set()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1.0)
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._process = None

    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return
        frame_size = self.width * self.height * 3
        while not self._stop.is_set():
            frame = _read_exact(process.stdout, frame_size)
            if frame is None:
                break
            self._on_frame(PreviewFrame(frame, self.width, self.height))
        if not self._stop.is_set():
            self._on_status("Camera test preview stopped; Linkable Camera is no longer readable.")


def _read_exact(stream: object, length: int) -> bytes | None:
    chunks = bytearray()
    read = getattr(stream, "read")
    while len(chunks) < length:
        chunk = read(length - len(chunks))
        if not chunk:
            return None
        chunks.extend(chunk)
    return bytes(chunks)
