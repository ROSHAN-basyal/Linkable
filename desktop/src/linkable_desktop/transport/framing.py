from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from socket import socket

from linkable_desktop.proto import common_pb2


def _read_exact(stream: io.BufferedIOBase, length: int) -> bytes:
    data = bytearray()
    while len(data) < length:
        chunk = stream.read(length - len(data))
        if not chunk:
            raise EOFError("unexpected end of stream")
        data.extend(chunk)
    return bytes(data)


def read_envelope(stream: io.BufferedIOBase, max_frame_size: int = 1_048_576) -> common_pb2.Envelope:
    header = _read_exact(stream, 4)
    (size,) = struct.unpack(">I", header)
    if size <= 0 or size > max_frame_size:
        raise ValueError(f"invalid frame size: {size}")
    payload = _read_exact(stream, size)
    envelope = common_pb2.Envelope()
    envelope.ParseFromString(payload)
    return envelope


def write_envelope(stream: io.BufferedIOBase, envelope: common_pb2.Envelope) -> None:
    payload = envelope.SerializeToString()
    stream.write(struct.pack(">I", len(payload)))
    stream.write(payload)
    stream.flush()


@dataclass(slots=True)
class ConnectionIO:
    sock: socket
    stream: io.BufferedIOBase = field(init=False)

    def __post_init__(self) -> None:
        self.stream = self.sock.makefile("rwb")

    def read_envelope(self, max_frame_size: int = 1_048_576) -> common_pb2.Envelope:
        return read_envelope(self.stream, max_frame_size=max_frame_size)

    def write_envelope(self, envelope: common_pb2.Envelope) -> None:
        write_envelope(self.stream, envelope)

    def close(self) -> None:
        try:
            try:
                self.stream.close()
            except OSError:
                pass
        finally:
            self.sock.close()
