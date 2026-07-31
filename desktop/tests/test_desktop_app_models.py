from __future__ import annotations

import unittest
from pathlib import Path

from linkable_desktop.app.devices import ActiveDevice, DeviceAvailability, build_device_models
from linkable_desktop.app.runtime import DesktopRuntime, RuntimePrompts
from linkable_desktop.config import default_discovery_config
from linkable_desktop.discovery.fallback import parse_direct_connect_endpoint
from linkable_desktop.proto import bluetooth_pb2
from linkable_desktop.trust.device_record import TrustedDeviceRecord


class DesktopAppModelTests(unittest.TestCase):
    def test_new_default_port_is_linkable_control_port(self) -> None:
        self.assertEqual(default_discovery_config().service_port, 37891)
        self.assertEqual(parse_direct_connect_endpoint("192.168.1.20").port, 37891)

    def test_device_models_merge_trust_and_runtime_state(self) -> None:
        record = TrustedDeviceRecord.from_public_key(
            device_id="A001",
            device_name="Phone",
            public_key_bytes=b"public-key",
            paired_at_epoch_ms=1000,
        )
        models = build_device_models(
            [record],
            {"A001": ActiveDevice("A001", "Phone", "192.168.1.64:37891", 10.0)},
            set(),
        )
        self.assertEqual(models[0].availability, DeviceAvailability.CONNECTED)
        self.assertEqual(models[0].endpoint, "192.168.1.64:37891")

    def test_device_models_include_matching_bluetooth_state(self) -> None:
        record = TrustedDeviceRecord.from_public_key(
            device_id="A001",
            device_name="Phone",
            public_key_bytes=b"public-key",
            paired_at_epoch_ms=1000,
        )
        models = build_device_models(
            [record],
            {"A001": ActiveDevice("A001", "Phone", "192.168.1.64:37891", 10.0)},
            set(),
            {"A001"},
        )

        self.assertTrue(models[0].bluetooth_connected)

    def test_runtime_prompts_records_trusted_session_endpoint_without_log_parsing(self) -> None:
        connected: list[ActiveDevice] = []
        prompts = RuntimePrompts(
            on_log=lambda message: None,
            on_device_connected=connected.append,
            on_device_closed=lambda device_id: None,
            confirm_pairing=lambda phone_name, device_id, address: True,
            prompt_code=lambda: "000000",
            on_notification_posted=lambda notification: None,
            on_notification_removed=lambda notification_id: None,
            on_call_status=lambda message: None,
            on_shared_apps=lambda snapshot: None,
            on_shared_app_launch_result=lambda result: None,
            on_phone_file_list=lambda response: None,
            on_phone_file_pull_result=lambda result: None,
            on_file_received=lambda result: None,
            on_contacts=lambda response: None,
            on_recent_contacts=lambda response: None,
            on_camera_capability=lambda response: None,
            on_camera_start_result=lambda result: None,
            on_camera_stop_result=lambda result: None,
            on_camera_status=lambda event: None,
            on_camera_frame=lambda frame: None,
            on_clipboard_update=lambda update: None,
        )

        prompts.record_trusted_session_started("A001", "PHONEID", "192.168.1.64:55892")

        self.assertEqual(len(connected), 1)
        self.assertEqual(connected[0].device_id, "PHONEID")
        self.assertEqual(connected[0].endpoint, "192.168.1.64:55892")

    def test_runtime_keeps_last_known_phone_host_after_session_drop(self) -> None:
        runtime = DesktopRuntime(
            root_dir=Path.cwd(),
            on_log=lambda message: None,
            on_devices_changed=lambda: None,
            confirm_pairing=lambda phone_name, device_id, address: True,
            prompt_code=lambda: "000000",
        )
        runtime._known_device_endpoints["A001"] = "192.168.1.64:45356"
        runtime._last_connected_device_id = "A001"

        self.assertEqual(runtime._active_phone_host(), "192.168.1.64")

    def test_runtime_records_phone_bluetooth_status_for_device_icon(self) -> None:
        runtime = DesktopRuntime(
            root_dir=Path.cwd(),
            on_log=lambda message: None,
            on_devices_changed=lambda: None,
            confirm_pairing=lambda phone_name, device_id, address: True,
            prompt_code=lambda: "000000",
        )

        runtime._record_bluetooth_status("A001", bluetooth_pb2.BluetoothAssistPhoneStatus(desktop_connected=True))

        self.assertIn("A001", runtime._bluetooth_connected_devices)


if __name__ == "__main__":
    unittest.main()
