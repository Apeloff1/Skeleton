"""Fail-closed native Godot pin acceptance (source-only tests)."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from skeleton.godot_export import binary
from skeleton.godot_export.certify import Options, certify


class EnginePinGateTests(TestCase):
    def test_wrong_engine_never_imports_project(self):
        with TemporaryDirectory() as td:
            runner = SimpleNamespace(version=lambda cwd: SimpleNamespace(ok=True, code=0, output="4.6.0.stable.official"))
            with patch("skeleton.godot_export.certify.import_cert.certify", side_effect=AssertionError("unsafe import")):
                report = certify(Path(td), Options(pin=binary.Pin("4.7.2")), runner)
            self.assertFalse(report.results[0].passed)
            self.assertEqual(len(report.results), 1)

    def test_missing_pinned_binary_never_imports_project(self):
        with TemporaryDirectory() as td:
            runner = SimpleNamespace(version=lambda cwd: SimpleNamespace(ok=True, code=0, output="4.7.2.stable.official"))
            with patch("skeleton.godot_export.certify.binary.check_version", return_value=binary.CaseResult("GFB-01", True, "matched")):
                with patch("skeleton.godot_export.certify.import_cert.certify", side_effect=AssertionError("unsafe import")):
                    report = certify(Path(td), Options(pin=binary.Pin("4.7.2", "a" * 64)), runner)
            self.assertFalse(report.results[-1].passed)
            self.assertEqual(report.results[-1].case_id, "GFB-02")

    def test_mismatched_digest_never_imports_project(self):
        with TemporaryDirectory() as td:
            executable = Path(td) / "godot"
            executable.write_bytes(b"not the pinned engine")
            runner = SimpleNamespace(version=lambda cwd: SimpleNamespace(ok=True, code=0, output="4.7.2.stable.official"))
            with patch("skeleton.godot_export.certify.binary.check_version", return_value=binary.CaseResult("GFB-01", True, "matched")):
                with patch("skeleton.godot_export.certify.import_cert.certify", side_effect=AssertionError("unsafe import")):
                    report = certify(Path(td), Options(godot=str(executable), pin=binary.Pin("4.7.2", "0" * 64)), runner)
            self.assertFalse(report.results[-1].passed)
            self.assertEqual(report.results[-1].case_id, "GFB-02")
