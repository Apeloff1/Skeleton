"""Offline Jeeves launcher admission: real argv and controlled headless holds.

These tests never instantiate a real Tk window, start an engine or run GGUF.
"""
from __future__ import annotations

from contextlib import redirect_stderr
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from skeleton.ai.runtime.operational_ai.laptop_runtime import desktop_app


class DesktopLaunchAdmissionTests(unittest.TestCase):
    def test_python_module_inspects_real_process_arguments(self):
        with patch.object(sys, "argv", ["desktop_app", "--provider-key", "secret"]):
            with self.assertRaisesRegex(SystemExit, "no prompt or secret arguments"):
                desktop_app.main()
        # The argument guard must take effect before any Tk display creation.

    def test_explicit_nonempty_argv_is_rejected_even_on_headless_system(self):
        with patch.object(desktop_app, "tk", None):
            with self.assertRaisesRegex(SystemExit, "no prompt or secret arguments"):
                desktop_app.main(["--prompt=hidden"])

    def test_no_tk_dependency_reports_controlled_hold(self):
        err = io.StringIO()
        with patch.object(desktop_app, "tk", None):
            with redirect_stderr(err):
                result = desktop_app.main([])
        self.assertEqual(result, 78)
        self.assertIn("requires Python tkinter", err.getvalue())
        self.assertIn("No model, state, or hosted provider was started", err.getvalue())

    def test_headless_display_failure_does_not_leak_os_exception(self):
        class FakeTclError(Exception):
            pass

        def missing_display():
            raise FakeTclError("DISPLAY=/private/operator/session")

        err = io.StringIO()
        with patch.object(desktop_app, "tk", SimpleNamespace(TclError=FakeTclError)):
            with patch.object(desktop_app, "JeevesWindow", missing_display):
                with redirect_stderr(err):
                    result = desktop_app.main([])
        self.assertEqual(result, 78)
        self.assertIn("working graphical display", err.getvalue())
        self.assertNotIn("DISPLAY=/private", err.getvalue())

    def test_valid_no_arg_launch_starts_only_one_gui_loop(self):
        loops = []

        class FakeWindow:
            def mainloop(self):
                loops.append("mainloop")

        with patch.object(desktop_app, "tk", SimpleNamespace(TclError=Exception)):
            with patch.object(desktop_app, "JeevesWindow", FakeWindow):
                self.assertEqual(desktop_app.main([]), 0)
        self.assertEqual(loops, ["mainloop"])

    def test_shell_launcher_forwards_all_untrusted_arguments_to_guard(self):
        repo_root = Path(__file__).resolve().parents[2]
        launcher = (repo_root / "jeeves-desktop.sh").read_text(encoding="utf-8")
        self.assertIn('exec python3 -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_app "$@"', launcher)
        self.assertIn("set -eu", launcher)
        self.assertNotIn("curl ", launcher)
        self.assertNotIn("wget ", launcher)
        self.assertNotIn("pip install ", launcher)


if __name__ == "__main__":
    unittest.main()
