"""Regression tests for source-level Godot export artifact custody."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skeleton.godot_export.runner import GodotRunner, RunResult


class VerifiedExportTests(unittest.TestCase):
    def test_new_artifact_success(self):
        with tempfile.TemporaryDirectory() as root:
            project = Path(root)
            def execute(argv, cwd, timeout):
                (cwd / "game.exe").write_bytes(b"binary")
                return RunResult(0, "ok", tuple(argv))
            result = GodotRunner("godot", exec_fn=execute).export_verified(
                project, "Windows Desktop", "game.exe"
            )
            self.assertTrue(result.ok)

    def test_exit_zero_without_artifact_is_failure(self):
        with tempfile.TemporaryDirectory() as root:
            result = GodotRunner(
                "godot", exec_fn=lambda argv, cwd, timeout: RunResult(0, "ok", tuple(argv))
            ).export_verified(Path(root), "Windows Desktop", "game.exe")
            self.assertEqual(result.code, 74)

    def test_existing_artifact_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "game.exe"
            target.write_bytes(b"old")
            def forbidden(argv, cwd, timeout):
                self.fail("Godot must not launch for an occupied destination")
            result = GodotRunner("godot", exec_fn=forbidden).export_verified(
                Path(root), "Windows Desktop", "game.exe"
            )
            self.assertEqual(result.code, 73)
            self.assertEqual(target.read_bytes(), b"old")

    def test_empty_and_directory_outputs_fail(self):
        for kind in ("empty", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                project = Path(root)
                def execute(argv, cwd, timeout):
                    output = cwd / "game.exe"
                    if kind == "empty":
                        output.touch()
                    else:
                        output.mkdir()
                    return RunResult(0, "ok", tuple(argv))
                result = GodotRunner("godot", exec_fn=execute).export_verified(
                    project, "Windows Desktop", "game.exe"
                )
                self.assertEqual(result.code, 74)

    def test_invalid_preset_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as root:
            def forbidden(argv, cwd, timeout):
                self.fail("invalid preset must not reach Godot")
            with self.assertRaises(ValueError):
                GodotRunner("godot", exec_fn=forbidden).export_verified(
                    Path(root), " ", "game.exe"
                )


if __name__ == "__main__":
    unittest.main()
