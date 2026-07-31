from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from linkable_desktop.crypto.identity import DeviceIdentity
from linkable_desktop.pairing.pairing_server import _descriptor_from_identity
from linkable_desktop.session.auth import (
    SESSION_ACK_LABEL,
    build_session_signature_payload,
    generate_ephemeral_public_key_bytes,
    is_timestamp_fresh,
)


class SessionAuthTests(unittest.TestCase):
    def test_session_signature_payload_is_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = DeviceIdentity.load_or_create(root / "desktop.pem", device_name="desktop")
            descriptor = _descriptor_from_identity(identity, "1.0.0")
            ephemeral_public_key = generate_ephemeral_public_key_bytes()
            payload = build_session_signature_payload(
                label=SESSION_ACK_LABEL,
                descriptor=descriptor,
                ephemeral_public_key=ephemeral_public_key,
                issued_at_ms=1234,
            )
            signature = identity.sign(payload)
            self.assertTrue(identity.to_peer_identity().verify(payload, signature))

    def test_timestamp_freshness_window(self) -> None:
        self.assertTrue(is_timestamp_fresh(1_000, max_skew_ms=250, now_ms=1_200))
        self.assertFalse(is_timestamp_fresh(1_000, max_skew_ms=250, now_ms=1_300))


if __name__ == "__main__":
    unittest.main()
