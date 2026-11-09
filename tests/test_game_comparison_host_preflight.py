"""Host preflight distinguishes valid ROM metadata from an executable sandbox.

All tests are source-only or patch host signals. No game, BIOS, core or
network action is performed.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.jeeves.game_comparison_host_preflight import inspect_native_host_runtime


class NativeEmulatorHostPreflightTests(unittest.TestCase):
    def test_nonlinux_host_fails_closed(self):
        with patch("skeleton.jeeves.game_comparison_host_preflight.sys.platform","win32"):
            result=inspect_native_host_runtime()
        self.assertFalse(result["native_launch_preflight_passed"])
        self.assertIn("native_host_requires_linux",
                      [entry["code"] for entry in result["blockers"]])
        self.assertFalse(result["native_rom_booted"])

    def test_absent_bwrap_reports_actionable_blocker(self):
        with patch("skeleton.jeeves.game_comparison_host_preflight.shutil.which",
                   return_value=None):
            result=inspect_native_host_runtime()
        self.assertFalse(result["native_launch_preflight_passed"])
        self.assertIn("bubblewrap_missing",
                      [entry["code"] for entry in result["blockers"]])
        self.assertEqual(result["sandbox_probe"]["status"],"not_requested")

    def test_probe_does_not_run_when_static_prerequisites_missing(self):
        with patch("skeleton.jeeves.game_comparison_host_preflight.shutil.which",
                   return_value=None), patch(
                       "skeleton.jeeves.game_comparison_host_preflight.subprocess.run"
                   ) as runner:
            result=inspect_native_host_runtime(probe_sandbox=True)
        runner.assert_not_called()
        self.assertFalse(result["sandbox_probe"]["attempted"])

    def test_probe_type_validation(self):
        with self.assertRaises(ValueError):
            inspect_native_host_runtime(probe_sandbox="true")


if __name__=="__main__":
    unittest.main()
