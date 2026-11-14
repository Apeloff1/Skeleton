"""Current-API regressions adapted from historical Godot export-custody coverage.

The binary signature here is a fixture, NOT native Godot/export release proof.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from skeleton.godot_export.artifact_custody import (
    ExportCustodyError, export_and_inspect, inspect_export,
)
from skeleton.godot_export.runner import GodotRunner, RunResult


PE_FIXTURE = b"MZ\x90\x00" + b"fixture-original-game-data"


class CurrentExportCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "game.exe"
        self.calls = []

    def runner(self, code=0, data=PE_FIXTURE):
        def execute(argv, cwd, timeout):
            self.calls.append((tuple(argv), cwd, timeout))
            if code == 0 and data is not None:
                self.target.write_bytes(data)
            return RunResult(code, "fixture engine result", tuple(argv))
        return GodotRunner("godot", exec_fn=execute)

    def test_real_bytes_not_process_exit_determine_digest(self):
        evidence = export_and_inspect(
            self.runner(), self.root, "Windows Desktop", self.target, "windows"
        )
        self.assertEqual(evidence.sha256, sha256(PE_FIXTURE).hexdigest())
        self.assertEqual(evidence.size, len(PE_FIXTURE))
        self.assertEqual(evidence.platform, "windows")
        self.assertIn("--export-release", self.calls[0][0])

    def test_engine_failure_is_never_custody_proof(self):
        with self.assertRaisesRegex(ExportCustodyError, "godot-export-failed"):
            export_and_inspect(
                self.runner(code=1), self.root, "Windows Desktop", self.target, "windows"
            )

    def test_empty_and_wrong_signature_are_rejected(self):
        for data in (b"", b"invalid-executable"):
            with self.subTest(data=data):
                self.target.unlink(missing_ok=True)
                with self.assertRaises(ExportCustodyError):
                    export_and_inspect(
                        self.runner(data=data), self.root, "Windows Desktop", self.target, "windows"
                    )

    def test_existing_artifact_is_never_overwritten_or_executed(self):
        self.target.write_bytes(b"previous")
        with self.assertRaisesRegex(ExportCustodyError, "output-already-exists"):
            export_and_inspect(
                self.runner(), self.root, "Windows Desktop", self.target, "windows"
            )
        self.assertEqual(self.target.read_bytes(), b"previous")
        self.assertEqual(self.calls, [])

    def test_symlink_destination_is_rejected_before_export(self):
        other = self.root / "other"
        other.write_bytes(b"preserve")
        self.target.symlink_to(other)
        with self.assertRaisesRegex(ExportCustodyError, "output-already-exists"):
            export_and_inspect(
                self.runner(), self.root, "Windows Desktop", self.target, "windows"
            )
        self.assertEqual(other.read_bytes(), b"preserve")
        self.assertEqual(self.calls, [])

    def test_failed_export_can_retry_in_clean_private_workspace(self):
        with self.assertRaises(ExportCustodyError):
            export_and_inspect(
                self.runner(code=1), self.root, "Windows Desktop", self.target, "windows"
            )
        self.assertFalse(self.target.exists())
        evidence = export_and_inspect(
            self.runner(), self.root, "Windows Desktop", self.target, "windows"
        )
        self.assertEqual(evidence.size, len(PE_FIXTURE))

    def test_inspection_rejects_outside_root_and_unsupported_platform(self):
        self.target.write_bytes(PE_FIXTURE)
        ok = RunResult(0, "fixture")
        with tempfile.TemporaryDirectory() as elsewhere:
            with self.assertRaises(ExportCustodyError):
                inspect_export(self.target, "windows", root=Path(elsewhere), result=ok)
        with self.assertRaisesRegex(ExportCustodyError, "unsupported-platform"):
            inspect_export(self.target, "unknown", root=self.root, result=ok)


if __name__ == "__main__":
    unittest.main()
