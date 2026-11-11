"""Deterministic positive/negative/restart custody tests (not native gameplay)."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from skeleton.godot_export.artifact_custody import (
    ExportCustodyError, export_and_inspect, inspect_export,
)
from skeleton.godot_export.runner import RunResult


class FakeRunner:
    def __init__(self, payload: bytes, code: int = 0):
        self.payload = payload
        self.code = code
        self.calls = 0

    def export(self, project, preset, out, timeout=600):
        self.calls += 1
        if self.code == 0:
            Path(out).write_bytes(self.payload)
        return RunResult(self.code, "", ("godot",))


class ArtifactCustodyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.output = self.root / "game.exe"

    def test_windows_binary_custody_and_cold_reinspection(self):
        payload = b"MZ" + bytes(128)
        runner = FakeRunner(payload)
        evidence = export_and_inspect(runner, self.project, "Windows Desktop", self.output, "windows")
        self.assertEqual(evidence.sha256, hashlib.sha256(payload).hexdigest())
        self.assertEqual(evidence.size, len(payload))
        self.assertEqual(runner.calls, 1)
        reopened = inspect_export(self.output, "windows", root=self.root, result=RunResult(0, ""))
        self.assertEqual(reopened.sha256, evidence.sha256)

    def test_linux_elf(self):
        payload = b"\x7fELF" + bytes(256)
        evidence = export_and_inspect(FakeRunner(payload), self.project, "Linux", self.root / "game.x86_64", "linux")
        self.assertEqual(evidence.size, len(payload))

    def test_linux_escaped_text_header_rejected(self):
        # ASCII backslash-x7f is not the four-byte ELF magic sequence.
        payload = b"\\x7fELF" + bytes(256)
        with self.assertRaisesRegex(ExportCustodyError, "invalid-elf-signature"):
            export_and_inspect(
                FakeRunner(payload), self.project, "Linux",
                self.root / "fake-elf", "linux",
            )

    def test_bad_header_fails_closed(self):
        with self.assertRaisesRegex(ExportCustodyError, "invalid-pe-signature"):
            export_and_inspect(FakeRunner(b"not-a-binary"), self.project, "Windows", self.output, "windows")

    def test_failed_process_never_certifies(self):
        with self.assertRaisesRegex(ExportCustodyError, "godot-export-failed"):
            export_and_inspect(FakeRunner(b"", code=127), self.project, "Windows", self.output, "windows")

    def test_existing_artifact_is_not_clobbered(self):
        self.output.write_bytes(b"previous")
        runner = FakeRunner(b"MZnew")
        with self.assertRaisesRegex(ExportCustodyError, "output-already-exists"):
            export_and_inspect(runner, self.project, "Windows", self.output, "windows")
        self.assertEqual(runner.calls, 0)
        self.assertEqual(self.output.read_bytes(), b"previous")

    def test_symlink_is_not_followed(self):
        target = self.root / "private"
        target.write_bytes(b"MZsecret")
        self.output.symlink_to(target)
        with self.assertRaises(ExportCustodyError):
            inspect_export(self.output, "windows", root=self.root, result=RunResult(0, ""))

    def test_outside_root_rejected(self):
        self.output.write_bytes(b"MZhello")
        with self.assertRaisesRegex(ExportCustodyError, "artifact-outside-export-root"):
            inspect_export(self.output, "windows", root=self.project, result=RunResult(0, ""))

    def test_unsupported_platform_rejected(self):
        self.output.write_bytes(b"MZhello")
        with self.assertRaisesRegex(ExportCustodyError, "unsupported-platform"):
            inspect_export(self.output, "console", root=self.root, result=RunResult(0, ""))

    def test_empty_artifact_rejected(self):
        with self.assertRaisesRegex(ExportCustodyError, "artifact-size-invalid"):
            export_and_inspect(FakeRunner(b""), self.project, "Windows", self.output, "windows")


if __name__ == "__main__":
    unittest.main()
