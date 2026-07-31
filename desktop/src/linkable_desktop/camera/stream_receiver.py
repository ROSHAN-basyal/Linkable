from __future__ import annotations

import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Thread


MAGIC = b"LINKABLE_CAMERA_MJPEG_V1\n"
MAX_FRAME_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class CameraServerState:
    """Runtime state for the short-lived camera media receiver."""

    host: str
    port: int
    token: str


class CameraFrameServer:
    """One-shot TCP receiver for authenticated mobile camera MJPEG frames."""

    def __init__(
        self,
        *,
        token: str,
        on_frame: Callable[[bytes], None],
        on_status: Callable[[str], None],
        bind_host: str = "0.0.0.0",
    ) -> None:
        self._token = token
        self._on_frame = on_frame
        self._on_status = on_status
        self._bind_host = bind_host
        self._stop = Event()
        self._thread: Thread | None = None
        self._socket: socket.socket | None = None
        self.state: CameraServerState | None = None

    def start(self) -> CameraServerState:
        """Bind a local port and start accepting one mobile camera stream."""

        if self._thread is not None:
            raise RuntimeError("camera receiver is already running")
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self._bind_host, 0))
        server.listen(1)
        server.settimeout(1.0)
        host, port = server.getsockname()
        self._socket = server
        self.state = CameraServerState(host=host, port=int(port), token=self._token)
        self._thread = Thread(target=self._run, name="linkable-camera-receiver", daemon=True)
        self._thread.start()
        return self.state

    def stop(self) -> None:
        """Stop accepting/reading frames and close the receiver socket."""

        self._stop.set()
        if self._socket is not None:
            run_close = self._socket.close
            try:
                run_close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        self._thread = None
        self._socket = None

    def _run(self) -> None:
        server = self._socket
        if server is None:
            return
        self._on_status("Camera receiver is waiting for the phone stream.")
        while not self._stop.is_set():
            try:
                client, address = server.accept()
                break
            except socket.timeout:
                continue
            except OSError as exc:
                if not self._stop.is_set():
                    self._on_status(f"Camera receiver stopped: {exc}")
                return
        else:
            return

        with client:
            client.settimeout(3.0)
            self._on_status(f"Camera stream connected from {address[0]}:{address[1]}.")
            try:
                self._read_client(client)
            except (OSError, EOFError, ValueError) as exc:
                if not self._stop.is_set():
                    self._on_status(f"Camera stream ended: {exc}")

    def _read_client(self, client: socket.socket) -> None:
        magic = _read_exact(client, len(MAGIC))
        if magic != MAGIC:
            raise ValueError("invalid camera stream preamble")
        token_length = struct.unpack(">H", _read_exact(client, 2))[0]
        token = _read_exact(client, token_length).decode("utf-8", errors="replace")
        if token != self._token:
            raise ValueError("camera stream token mismatch")
        while not self._stop.is_set():
            header = _read_exact(client, 4)
            frame_size = struct.unpack(">I", header)[0]
            if frame_size <= 0 or frame_size > MAX_FRAME_BYTES:
                raise ValueError(f"invalid camera frame size: {frame_size}")
            self._on_frame(_read_exact(client, frame_size))


def _read_exact(sock: socket.socket, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            raise EOFError("camera stream closed")
        data.extend(chunk)
    return bytes(data)
