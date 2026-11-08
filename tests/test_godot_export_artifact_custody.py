"""Positive, negative, and retry regression tests for actual Godot export custody."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from skeleton.godot_export.artifact_custody import export_with_evidence
from skeleton.godot_export.runner import GodotRunner, RunResult


class ExportCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "game.pck"
        self.calls = []

    def runner(self, code=0, data=b"original game data"):
        def execute(argv, cwd, timeout):
            self.calls.append((argv, cwd, timeout))
            if code == 0:
                self.target.write_bytes(data)
            return RunResult(code, "Godot result", tuple(argv))
        return GodotRunner("godot", execute)

    def test_export_produces_hash_of_real_bytes(self):
        result = export_with_evidence(self.runner(), self.root, "Windows", self.target)
        self.assertTrue(result.verified)
        self.assertEqual(result.sha256, hashlib.sha256(b"original game data").hexdigest())
        self.assertEqual(result.size, len(b"original game data"))
        self.assertIn("--export-release", self.calls[0][0])

    def test_engine_failure_not_certified(self):
        result = export_with_evidence(self.runner(code=1), self.root, "Windows", self.target)
        self.assertEqual(result.failure, "engine_export_failed")

    def test_empty_artifact_rejected(self):
        result = export_with_evidence(self.runner(data=b""), self.root, "Windows", self.target)
        self.assertEqual(result.failure, "invalid_artifact")

    def test_oversize_artifact_rejected(self):
        result = export_with_evidence(self.runner(), self.root, "Windows", self.target, max_bytes=3)
        self.assertEqual(result.failure, "invalid_artifact")

    def test_existing_artifact_not_overwritten(self):
        self.target.write_bytes(b"previous")
        result = export_with_evidence(self.runner(), self.root, "Windows", self.target)
        self.assertEqual(result.failure, "artifact_already_exists")
        self.assertEqual(self.target.read_bytes(), b"previous")
        self.assertEqual(self.calls, [])

    def test_symlink_destination_rejected(self):
        other = self.root / "other"
        other.write_bytes(b"preserve")
        self.target.symlink_to(other)
        result = export_with_evidence(self.runner(), self.root, "Windows", self.target)
        self.assertFalse(result.verified)
        self.assertEqual(other.read_bytes(), b"preserve")
        self.assertFalse(self.calls)

    def test_outside_project_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            result = export_with_evidence(self.runner(), self.root, "Windows", Path(external) / "out.pck")
        self.assertEqual(result.failure, "unsafe_artifact_path")
        self.assertFalse(self.calls)

    def test_boolean_budget_rejected(self):
        result = export_with_evidence(self.runner(), self.root, "Windows", self.target, max_bytes=True)
        self.assertEqual(result.failure, "invalid_size_budget")
        self.assertFalse(self.calls)

    def test_failed_export_can_retry_after_cleanup(self):
        first = export_with_evidence(self.runner(code=1), self.root, "Windows", self.target)
        second = export_with_evidence(self.runner(), self.root, "Windows", self.target)
        self.assertFalse(first.verified)
        self.assertTrue(second.verified)

    def test_missing_output_after_success_rejected(self):
        def no_output(argv, cwd, timeout):
            return RunResult(0, "success")
        result = export_with_evidence(GodotRunner("godot", no_output), self.root, "Windows", self.target)
        self.assertEqual(result.failure, "artifact_unreadable")


if __name__ == "__main__":
    unittest.main()
