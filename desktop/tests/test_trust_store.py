from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from linkable_desktop.trust.device_record import TrustedDeviceRecord
from linkable_desktop.trust.trust_store import TrustStore


class TrustStoreTests(unittest.TestCase):
    def test_upsert_and_get(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustStore(Path(tmp) / "trusted.json")
            record = TrustedDeviceRecord.from_public_key(
                device_id="ABC123",
                device_name="Phone",
                public_key_bytes=b"pubkey",
                paired_at_epoch_ms=123456,
            )
            store.upsert(record)
            loaded = store.get("ABC123")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.device_name, "Phone")
            self.assertEqual(loaded.public_key_bytes, b"pubkey")

    def test_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = TrustStore(Path(tmp) / "trusted.json")
            record = TrustedDeviceRecord.from_public_key(
                device_id="ABC123",
                device_name="Phone",
                public_key_bytes=b"pubkey",
                paired_at_epoch_ms=123456,
            )
            store.upsert(record)
            self.assertTrue(store.remove("ABC123"))
            self.assertIsNone(store.get("ABC123"))
            self.assertFalse(store.remove("ABC123"))


if __name__ == "__main__":
    unittest.main()
