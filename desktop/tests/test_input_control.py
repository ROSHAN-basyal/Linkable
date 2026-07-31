import unittest

import linkable_desktop.input.control as control
from linkable_desktop.input.control import DesktopInputController, InputCommandResult
from linkable_desktop.proto import input_pb2


class DesktopInputControllerTest(unittest.TestCase):
    def test_text_requires_ydotool(self) -> None:
        controller = DesktopInputController()
        controller.ydotool = ""
        result = controller.execute(
            input_pb2.DesktopInputRequest(
                action_type=input_pb2.DESKTOP_INPUT_ACTION_TYPE_TEXT,
                text="hello",
            )
        )
        self.assertFalse(result.success)
        self.assertIn("ydotool", result.detail)

    def test_volume_clamps_without_backend_erroring(self) -> None:
        controller = DesktopInputController()
        controller.wpctl = ""
        controller.pactl = ""
        result = controller.execute(
            input_pb2.DesktopInputRequest(
                action_type=input_pb2.DESKTOP_INPUT_ACTION_TYPE_VOLUME_SET,
                volume_percent=500,
            )
        )
        self.assertFalse(result.success)
        self.assertIn("wpctl", result.detail)

    def test_key_combo_uses_ydotool_press_release_events(self) -> None:
        controller = DesktopInputController()
        controller.ydotool = "/usr/bin/ydotool"
        calls: list[tuple[str, ...]] = []

        def fake_run(command: tuple[str, ...]) -> InputCommandResult:
            calls.append(command)
            return InputCommandResult(True, "ok")

        original_run = control._run
        try:
            control._run = fake_run
            result = controller.execute(
                input_pb2.DesktopInputRequest(
                    action_type=input_pb2.DESKTOP_INPUT_ACTION_TYPE_KEY_COMBO,
                    key_combo=("ctrl", "backspace"),
                )
            )
        finally:
            control._run = original_run

        self.assertTrue(result.success)
        self.assertEqual(calls, [("/usr/bin/ydotool", "key", "29:1", "14:1", "14:0", "29:0")])


if __name__ == "__main__":
    unittest.main()
