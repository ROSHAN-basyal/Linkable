from __future__ import annotations

import unittest

from linkable_desktop.bluetooth.hfp import (
    first_hfp_profile,
    parse_bluetooth_device_lines,
    parse_controller_address,
    parse_key_values,
    parse_pactl_card_infos,
    parse_pactl_card_profiles,
    parse_pactl_cards,
    validate_bluetooth_address,
)


class HfpParsingTests(unittest.TestCase):
    def test_parse_bluetoothctl_devices(self) -> None:
        devices = parse_bluetooth_device_lines(
            "Device AA:BB:CC:DD:EE:FF Pixel 7\nDevice 11:22:33:44:55:66 Headset\n"
        )
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(devices[0].name, "Pixel 7")

    def test_parse_key_values(self) -> None:
        values = parse_key_values("Powered: yes\nDiscoverable: no\nAlias: Laptop\n")
        self.assertEqual(values["Powered"], "yes")
        self.assertEqual(values["Alias"], "Laptop")

    def test_parse_controller_address_from_bluetoothctl_show(self) -> None:
        self.assertEqual(
            parse_controller_address(
                """
Controller B4:8C:9D:2D:FE:26 (public)
    Alias: rbsylasusTUF
    Pairable: yes
                """
            ),
            "B4:8C:9D:2D:FE:26",
        )

    def test_parse_hfp_profiles_from_pactl_cards(self) -> None:
        cards = parse_pactl_cards(
            """
Card #42
    Name: bluez_card.AA_BB_CC_DD_EE_FF
    Profiles:
        off: Off (sinks: 0, sources: 0, priority: 0, available: yes)
        headset-head-unit-msbc: Headset Head Unit (HSP/HFP, codec mSBC) (sinks: 1, sources: 1, priority: 30, available: yes)
        a2dp-sink: High Fidelity Playback (A2DP Sink) (sinks: 1, sources: 0, priority: 40, available: no)
    Active Profile: off
            """
        )
        self.assertEqual(cards["bluez_card.AA_BB_CC_DD_EE_FF"], ["headset-head-unit-msbc"])

    def test_parse_all_available_profiles_from_pactl_cards(self) -> None:
        cards = parse_pactl_card_profiles(
            """
Card #42
    Name: bluez_card.AA_BB_CC_DD_EE_FF
    Profiles:
        off: Off (sinks: 0, sources: 0, priority: 0, available: yes)
        headset-head-unit-msbc: Headset Head Unit (HSP/HFP, codec mSBC) (sinks: 1, sources: 1, priority: 30, available: yes)
        a2dp-sink: High Fidelity Playback (A2DP Sink) (sinks: 1, sources: 0, priority: 40, available: no)
    Active Profile: off
            """
        )
        self.assertEqual(cards["bluez_card.AA_BB_CC_DD_EE_FF"], ["off", "headset-head-unit-msbc"])

    def test_parse_bluetooth_audio_card_identity(self) -> None:
        cards = parse_pactl_card_infos(
            """
Card #42
    Name: bluez_card.AA_BB_CC_DD_EE_FF
    Properties:
        device.alias = "CMF by Nothing Phone 2 Pro"
        device.description = "CMF by Nothing Phone 2 Pro"
        api.bluez5.address = "AA:BB:CC:DD:EE:FF"
    Profiles:
        off: Off (sinks: 0, sources: 0, priority: 0, available: yes)
        audio-gateway: Handsfree Audio Gateway (sinks: 1, sources: 1, priority: 30, available: yes)
    Active Profile: off
            """
        )
        self.assertEqual(cards[0].alias, "CMF by Nothing Phone 2 Pro")
        self.assertEqual(cards[0].address, "AA:BB:CC:DD:EE:FF")
        self.assertTrue(cards[0].matches_identity("CMF by Nothing Phone 2 Pro"))
        self.assertEqual(cards[0].hfp_profiles(), ("audio-gateway",))

    def test_first_hfp_profile_prefers_msbc(self) -> None:
        self.assertEqual(
            first_hfp_profile(["a2dp-sink", "headset-head-unit-cvsd", "headset-head-unit-msbc"]),
            "headset-head-unit-msbc",
        )

    def test_first_hfp_profile_accepts_phone_audio_gateway(self) -> None:
        self.assertEqual(first_hfp_profile(["off", "audio-gateway"]), "audio-gateway")

    def test_validate_bluetooth_address(self) -> None:
        validate_bluetooth_address("AA:BB:CC:DD:EE:FF")
        with self.assertRaises(ValueError):
            validate_bluetooth_address("not-a-mac")


if __name__ == "__main__":
    unittest.main()
