from __future__ import annotations

import unittest

from linkable_desktop.mirroring.scrcpy import ScrcpyManager, extract_ipv4_host, normalize_adb_target, parse_adb_devices


class ScrcpyMirroringTests(unittest.TestCase):
    def test_parse_adb_devices_with_usb_and_tcp(self) -> None:
        devices = parse_adb_devices(
            """
List of devices attached
001966566001213 device usb:1-2 product:phone model:CMF device:tetris transport_id:1
192.168.1.64:5555 device product:phone model:CMF device:tetris transport_id:2
emulator-5554 offline
            """
        )

        self.assertEqual(len(devices), 3)
        self.assertEqual(devices[0].serial, "001966566001213")
        self.assertFalse(devices[0].is_tcp)
        self.assertTrue(devices[1].is_tcp)
        self.assertFalse(devices[2].is_ready)

    def test_tcp_serial_adds_default_port(self) -> None:
        manager = ScrcpyManager()

        self.assertEqual(manager.tcp_serial("192.168.1.64"), "192.168.1.64:5555")
        self.assertEqual(manager.tcp_serial("192.168.1.64:45678"), "192.168.1.64:45678")

    def test_extract_ipv4_host_from_lan_peer_summary(self) -> None:
        self.assertEqual(
            extract_ipv4_host("Trusted reconnect accepted from A001 at 192.168.1.64:55892."),
            "192.168.1.64",
        )

    def test_normalize_adb_target_rejects_partial_ip(self) -> None:
        self.assertEqual(normalize_adb_target("192"), "")
        self.assertEqual(normalize_adb_target("192.168.1.64"), "192.168.1.64")
        self.assertEqual(normalize_adb_target("192.168.1.64:5555"), "192.168.1.64:5555")


if __name__ == "__main__":
    unittest.main()
