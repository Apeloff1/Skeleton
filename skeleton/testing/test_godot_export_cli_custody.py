"""Offline operator CLI source qualification; a mocked Godot runner is not a device test."""
from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.godot_export import cli
from skeleton.godot_export.artifact_custody import ExportEvidence


class GodotCustodyCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="godot-export-cli-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "original-game"
        self.project.mkdir()
        self.engine = self.root / "godot-synthetic"
        self.engine.write_bytes(b"synthetic-non-executable-godot-placeholder")
        self.pin = sha256(self.engine.read_bytes()).hexdigest()
        self.output = self.root / "original-game.exe"

    def _argv(self, *, pin=None, engine=None):
        return [
            "custody-export",
            "--project", str(self.project),
            "--preset", "Windows Desktop",
            "--output", str(self.output),
            "--platform", "windows",
            "--engine-bin", str(self.engine if engine is None else engine),
            "--engine-sha256", self.pin if pin is None else pin,
            "--engine-version", "4.7.2",
        ]

    def _invoke(self, argv=None):
        out = StringIO()
        with redirect_stdout(out):
            code = cli.main(self._argv() if argv is None else argv)
        return code, json.loads(out.getvalue())

    def test_pinned_version_and_custody_boundary(self):
        with (mock.patch.object(cli.binary, "check_version",
                                return_value=mock.Mock(passed=True)) as version,
              mock.patch.object(cli, "export_and_inspect",
                                return_value=ExportEvidence(
                                    str(self.output), "windows", 256,
                                    "a" * 64, 0)) as export):
            code, receipt = self._invoke()
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "source-artifact-inspected")
        self.assertEqual(receipt["artifact"]["sha256"], "a" * 64)
        self.assertFalse(receipt["release_certified"])
        self.assertFalse(receipt["device_qualified"])
        self.assertFalse(receipt["launch_tested"])
        self.assertEqual(export.call_count, 1)
        self.assertEqual(version.call_count, 1)
        self.assertEqual(export.call_args.kwargs["timeout"], 600)

    def test_bad_pin_is_refused_before_any_godot_process(self):
        with (mock.patch.object(cli.binary, "check_version") as version,
              mock.patch.object(cli, "export_and_inspect") as export):
            for pin in ("", "A" * 64, "f" * 63, "f" * 65):
                with self.subTest(pin=pin):
                    code, receipt = self._invoke(self._argv(pin=pin))
                    self.assertEqual(code, 2)
                    self.assertEqual(receipt["status"], "held")
            self.assertEqual(export.call_count, 0)
            self.assertEqual(version.call_count, 0)

    def test_wrong_pin_and_symlink_engine_refused(self):
        with (mock.patch.object(cli.binary, "check_version") as version,
              mock.patch.object(cli, "export_and_inspect") as export):
            code, receipt = self._invoke(self._argv(pin="f" * 64))
            self.assertEqual(code, 2)
            self.assertEqual(receipt["reason"], "engine-binary-pin-or-identity-mismatch")
            self.assertEqual(version.call_count, 0)
            link = self.root / "linked-godot"
            try:
                link.symlink_to(self.engine)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            code, receipt = self._invoke(self._argv(engine=link))
            self.assertEqual(code, 2)
            self.assertEqual(receipt["reason"], "engine-binary-invalid")
            self.assertEqual(export.call_count, 0)

    def test_failed_version_is_a_hold_not_a_release_verdict(self):
        with (mock.patch.object(cli.binary, "check_version",
                                return_value=mock.Mock(passed=False)),
              mock.patch.object(cli, "export_and_inspect") as export):
            code, receipt = self._invoke()
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "engine-version-mismatch")
        self.assertEqual(export.call_count, 0)
        self.assertFalse(receipt["release_certified"])

    def test_output_failure_is_held_without_success_claim(self):
        with (mock.patch.object(cli.binary, "check_version",
                                return_value=mock.Mock(passed=True)),
              mock.patch.object(cli, "export_and_inspect",
                                side_effect=ValueError("mocked failure"))):
            code, receipt = self._invoke()
        self.assertEqual(code, 2)
        self.assertEqual(receipt["reason"], "source-or-artifact-custody-rejected")
        self.assertFalse(receipt["device_qualified"])

    def test_existing_subcommands_and_parser_are_retained(self):
        commands = cli.build_parser()
        self.assertIsNotNone(commands.parse_args(["cases"]))
        with self.assertRaises(SystemExit):
            commands.parse_args(["custody-export"])


if __name__ == "__main__":
    unittest.main()
