from __future__ import annotations

import unittest

from linkable_desktop.discovery.fallback import parse_direct_connect_endpoint
from linkable_desktop.discovery import mdns_advertiser
from linkable_desktop.discovery.mdns_browser import DiscoveryRegistry, MdnsServiceListener


class FakeServiceInfo:
    def __init__(self) -> None:
        self.name = "Laptop._linkable._tcp.local."
        self.port = 7734
        self.addresses = [b"\x0a\x00\x00\x05"]
        self.properties = {
            b"device_name": b"Laptop",
            b"protocol_version": b"1.0.0",
            b"device_id": b"abc123",
        }


class DirectConnectParsingTests(unittest.TestCase):
    def test_host_port_parsing(self) -> None:
        candidate = parse_direct_connect_endpoint("192.168.1.10:9000")
        self.assertEqual(candidate.host, "192.168.1.10")
        self.assertEqual(candidate.port, 9000)

    def test_default_port(self) -> None:
        candidate = parse_direct_connect_endpoint("192.168.1.10", default_port=7734)
        self.assertEqual(candidate.port, 7734)

    def test_ipv6_with_brackets(self) -> None:
        candidate = parse_direct_connect_endpoint("[fe80::1]:7777")
        self.assertEqual(candidate.host, "fe80::1")
        self.assertEqual(candidate.port, 7777)


class MdnsRegistryTests(unittest.TestCase):
    def test_ingest_service_info(self) -> None:
        registry = DiscoveryRegistry()
        listener = MdnsServiceListener(registry)
        device = listener.ingest_service_info(FakeServiceInfo())
        self.assertIsNotNone(device)
        assert device is not None
        self.assertEqual(device.name, "Laptop")
        self.assertEqual(device.endpoint, "10.0.0.5:7734")
        self.assertEqual(len(registry.snapshot()), 1)


class MdnsAdvertiserTests(unittest.TestCase):
    def test_preferred_ipv4_is_advertised_first_and_solo(self) -> None:
        original_preferred = mdns_advertiser._preferred_ipv4_address
        original_hostname = mdns_advertiser._hostname_ipv4_addresses
        try:
            mdns_advertiser._preferred_ipv4_address = lambda: "192.168.1.64"
            mdns_advertiser._hostname_ipv4_addresses = lambda: ["172.17.0.1", "192.168.1.64"]
            addresses = mdns_advertiser._discover_ipv4_addresses()
        finally:
            mdns_advertiser._preferred_ipv4_address = original_preferred
            mdns_advertiser._hostname_ipv4_addresses = original_hostname

        self.assertEqual(addresses, [b"\xc0\xa8\x01@"])

    def test_falls_back_to_hostname_addresses_when_no_preferred_route(self) -> None:
        original_preferred = mdns_advertiser._preferred_ipv4_address
        original_hostname = mdns_advertiser._hostname_ipv4_addresses
        try:
            mdns_advertiser._preferred_ipv4_address = lambda: None
            mdns_advertiser._hostname_ipv4_addresses = lambda: ["172.17.0.1", "192.168.1.64"]
            addresses = mdns_advertiser._discover_ipv4_addresses()
        finally:
            mdns_advertiser._preferred_ipv4_address = original_preferred
            mdns_advertiser._hostname_ipv4_addresses = original_hostname

        self.assertEqual(addresses, [b"\xac\x11\x00\x01", b"\xc0\xa8\x01@"])


if __name__ == "__main__":
    unittest.main()
