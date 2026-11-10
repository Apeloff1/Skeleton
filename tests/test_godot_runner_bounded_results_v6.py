"""Regression tests for bounded Godot runner diagnostics and deadlines."""
from __future__ import annotations

import math
import sys
import tempfile
import unittest
from pathlib import Path

from skeleton.godot_export.runner import GodotRunner, RunResult, subprocess_exec, TAIL


class RunnerSafetyTests(unittest.TestCase):
    def test_reject_invalid_deadlines_without_spawning(self):
        calls = []
        runner = GodotRunner("godot", exec_fn=lambda *args: calls.append(args) or RunResult(0, "ok"))
        with tempfile.TemporaryDirectory() as tmp:
            for value in (0, -1, True, False, float("nan"), float("inf"), 3601, "60", None):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    runner.run([], Path(tmp), value)
        self.assertEqual(calls, [])

    def test_valid_deadline_reaches_injected_engine(self):
        calls = []
        runner = GodotRunner("godot", exec_fn=lambda *args: calls.append(args) or RunResult(0, "ok"))
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.run(["--version"], Path(tmp), 0.5)
        self.assertTrue(result.ok)
        self.assertEqual(calls[0][2], 0.5)

    def test_real_process_diagnostics_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess_exec([sys.executable, "-c", "print('x' * 10000)"], Path(tmp), 10)
        self.assertEqual(result.code, 0)
        self.assertLessEqual(len(result.output), TAIL)
        self.assertEqual(result.argv[0], sys.executable)

    def test_launch_failure_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess_exec([str(Path(tmp) / "missing-godot")], Path(tmp), 1)
        self.assertTrue(result.launch_failed)


if __name__ == "__main__":
    unittest.main()
