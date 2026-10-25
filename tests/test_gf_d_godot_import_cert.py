"""No-engine regression cases for fail-closed GF-D native certification."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import certify_game_frontier_godot_import as cert


class GodotImportCertificationTests(unittest.TestCase):
    def test_timeout_is_bounded_and_fails_with_engine_receipt(self) -> None:
        timed_out = subprocess.TimeoutExpired(
            ["godot", "--headless", "--import"], 1,
            output=b"partial stdout", stderr=b"partial stderr",
        )
        with tempfile.TemporaryDirectory() as root:
            with patch.object(cert.subprocess, "run", side_effect=timed_out):
                code, output = cert.run("godot", ["--import"], Path(root), 1)
        self.assertEqual(code, 124)
        self.assertIn("Godot timed out", output)
        self.assertIn("partial stdout", output)
        self.assertIn("partial stderr", output)

    def test_missing_engine_fails_with_bounded_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            with patch.object(cert.subprocess, "run", side_effect=FileNotFoundError("missing")):
                code, output = cert.run("godot", ["--import"], Path(root), 1)
        self.assertEqual(code, 127)
        self.assertEqual(output, "Godot launch failed: FileNotFoundError")

    def test_timeout_cannot_certify_a_project(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            project = Path(root)
            (project / "project.godot").write_text("[application]\n", encoding="utf-8")
            recorded = io.StringIO()
            with (
                patch.object(cert, "run", return_value=(124, "Godot timed out")),
                patch.object(sys, "argv", [
                    "certify_game_frontier_godot_import.py", "--godot", "godot",
                    "--project", str(project),
                ]),
                contextlib.redirect_stdout(recorded),
            ):
                code = cert.main()
        self.assertEqual(code, 1)
        report = json.loads(recorded.getvalue())
        self.assertFalse(report["pass"])
        self.assertIn("GFD-01", {entry["case"] for entry in report["fails"]})


if __name__ == "__main__":
    unittest.main()
