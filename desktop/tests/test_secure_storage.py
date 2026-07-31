from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from linkable_desktop.crypto.identity import DeviceIdentity
from linkable_desktop.secure_storage import atomic_write_private, ensure_private_directory
from linkable_desktop.trust.device_record import TrustedDeviceRecord
from linkable_desktop.trust.trust_store import TrustStore


class SecureStorageTests(unittest.TestCase):
    def test_private_directory_and_file_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            target = state / "config.json"
            ensure_private_directory(state)
            atomic_write_private(target, "{}\n")

            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

    def test_identity_and_trust_store_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "state"
            identity_path = state / "identity.pem"
            trust_path = state / "trust.json"
            identity = DeviceIdentity.load_or_create(identity_path, device_name="desktop")
            TrustStore(trust_path).upsert(
                TrustedDeviceRecord.from_public_key(
                    device_id="phone",
                    device_name="phone",
                    public_key_bytes=identity.public_key_bytes,
                    paired_at_epoch_ms=1,
                )
            )

            self.assertEqual(stat.S_IMODE(identity_path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(trust_path.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
