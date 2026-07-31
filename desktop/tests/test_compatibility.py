import unittest

from linkable_desktop.app import compatibility


class CompatibilityFirewallTests(unittest.TestCase):
    def test_firewall_check_is_noninteractive_when_firewalld_exists(self) -> None:
        original_which = compatibility.shutil.which
        original_run = compatibility._run_read_only
        called = False

        def fail_if_called(command: tuple[str, ...], timeout: float = 3.0):
            nonlocal called
            called = True
            raise AssertionError(f"unexpected command: {command}")

        try:
            compatibility.shutil.which = lambda name: "/usr/bin/firewall-cmd" if name == "firewall-cmd" else None
            compatibility._run_read_only = fail_if_called
            check = compatibility._firewall_check(7734)
        finally:
            compatibility.shutil.which = original_which
            compatibility._run_read_only = original_run

        self.assertTrue(check.ok)
        self.assertFalse(check.critical)
        self.assertIn("startup probing is disabled", check.detail)
        self.assertFalse(called)

    def test_firewall_check_passes_when_no_firewall_tool_exists(self) -> None:
        original_which = compatibility.shutil.which
        try:
            compatibility.shutil.which = lambda name: None
            check = compatibility._firewall_check(7734)
        finally:
            compatibility.shutil.which = original_which

        self.assertTrue(check.ok)
        self.assertEqual(check.fix_commands, ())


if __name__ == "__main__":
    unittest.main()
