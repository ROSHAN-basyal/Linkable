from __future__ import annotations

import io
import unittest

from linkable_desktop.proto import build_envelope, common_pb2, transport_pb2
from linkable_desktop.transport.framing import ConnectionIO


class FakeSocket:
    def __init__(self, stream: io.BytesIO) -> None:
        self.stream = stream
        self.makefile_calls: list[str] = []
        self.closed = False

    def makefile(self, mode: str) -> io.BytesIO:
        self.makefile_calls.append(mode)
        return self.stream

    def close(self) -> None:
        self.closed = True


class ConnectionIOTests(unittest.TestCase):
    def test_connection_io_initializes_stream_and_roundtrips_envelope(self) -> None:
        shared_stream = io.BytesIO()

        sender_socket = FakeSocket(shared_stream)
        receiver_socket = FakeSocket(shared_stream)

        sender = ConnectionIO(sender_socket)
        receiver = ConnectionIO(receiver_socket)

        ping = transport_pb2.Ping(token="hello")
        sender.write_envelope(
            build_envelope(
                common_pb2.PACKET_TYPE_PING,
                ping,
                sequence_number=1,
            )
        )

        shared_stream.seek(0)
        envelope = receiver.read_envelope()
        self.assertEqual(envelope.packet_type, common_pb2.PACKET_TYPE_PING)
        decoded = transport_pb2.Ping()
        decoded.ParseFromString(envelope.payload)
        self.assertEqual(decoded.token, "hello")
        self.assertEqual(sender_socket.makefile_calls, ["rwb"])
        self.assertEqual(receiver_socket.makefile_calls, ["rwb"])


if __name__ == "__main__":
    unittest.main()
