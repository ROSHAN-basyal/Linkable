from __future__ import annotations

import io
import unittest

from linkable_desktop.crypto.session_cipher import EncryptedEnvelopeChannel, derive_directional_keys
from linkable_desktop.proto import build_envelope, common_pb2, transport_pb2
from linkable_desktop.session.auth import generate_ephemeral_key_pair


class SessionCipherTests(unittest.TestCase):
    def test_directional_keys_match_and_channel_roundtrips(self) -> None:
        initiator = generate_ephemeral_key_pair()
        acceptor = generate_ephemeral_key_pair()
        initiator_keys = derive_directional_keys(
            private_key=initiator.private_key,
            peer_public_key_bytes=acceptor.public_key_bytes,
            initiator_public_key_bytes=initiator.public_key_bytes,
            acceptor_public_key_bytes=acceptor.public_key_bytes,
        )
        acceptor_keys = derive_directional_keys(
            private_key=acceptor.private_key,
            peer_public_key_bytes=initiator.public_key_bytes,
            initiator_public_key_bytes=initiator.public_key_bytes,
            acceptor_public_key_bytes=acceptor.public_key_bytes,
        )
        self.assertEqual(initiator_keys.client_to_server, acceptor_keys.client_to_server)
        self.assertEqual(initiator_keys.server_to_client, acceptor_keys.server_to_client)

        stream = io.BytesIO()
        sender = EncryptedEnvelopeChannel(
            stream=stream,
            send_key=initiator_keys.client_to_server,
            receive_key=initiator_keys.server_to_client,
        )
        receiver = EncryptedEnvelopeChannel(
            stream=stream,
            send_key=acceptor_keys.server_to_client,
            receive_key=acceptor_keys.client_to_server,
        )
        sender.write_envelope(
            build_envelope(
                common_pb2.PACKET_TYPE_PING,
                transport_pb2.Ping(token="m4"),
                sequence_number=1,
            )
        )
        stream.seek(0)
        envelope = receiver.read_envelope()
        self.assertEqual(envelope.packet_type, common_pb2.PACKET_TYPE_PING)


if __name__ == "__main__":
    unittest.main()
