from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from linkable_desktop.crypto.identity import DeviceIdentity
from linkable_desktop.pairing.code_generator import PairingChallengeMaterial
from linkable_desktop.pairing.pairing_server import ActiveSessionRegistry


class PairingCodeTests(unittest.TestCase):
    def test_pairing_code_matches_for_both_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            desktop = DeviceIdentity.load_or_create(root / "desktop.pem", device_name="desktop")
            android = DeviceIdentity.load_or_create(root / "android.pem", device_name="android")
            pairing_nonce = b"a" * 32
            challenge_nonce = b"b" * 32

            desktop_material = PairingChallengeMaterial(
                pairing_nonce=pairing_nonce,
                challenge_nonce=challenge_nonce,
                initiator_public_key=android.public_key_bytes,
                acceptor_public_key=desktop.public_key_bytes,
                initiator_device_id=android.device_id,
                acceptor_device_id=desktop.device_id,
            )
            android_material = PairingChallengeMaterial(
                pairing_nonce=pairing_nonce,
                challenge_nonce=challenge_nonce,
                initiator_public_key=android.public_key_bytes,
                acceptor_public_key=desktop.public_key_bytes,
                initiator_device_id=android.device_id,
                acceptor_device_id=desktop.device_id,
            )
            self.assertEqual(desktop_material.pairing_code(), android_material.pairing_code())
            self.assertEqual(desktop_material.transcript_hash(), android_material.transcript_hash())


class ActiveSessionRegistryTests(unittest.TestCase):
    def test_rejects_duplicate_session_for_same_device(self) -> None:
        registry = ActiveSessionRegistry()
        first_token = registry.acquire("phone-1")

        self.assertIsNotNone(first_token)
        self.assertIsNone(registry.acquire("phone-1"))

        registry.release(first_token or "")
        self.assertIsNotNone(registry.acquire("phone-1"))


if __name__ == "__main__":
    unittest.main()
