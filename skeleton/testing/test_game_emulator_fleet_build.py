"""Contract tests for the opt-in, failure-isolated emulator build dispatcher.

All native builds are mocked here. Passing these tests could not establish
that a libretro library compiled or booted any ROM.
"""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import install_game_emulator_cores as bootstrap


class EmulatorFleetBuildTests(unittest.TestCase):
    def test_failure_does_not_cancel_other_explicit_cores(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(
                core=["sameboy", "nestopia", "mesen"],
                install_root=Path(directory),
            )
            attempted = []

            def fake_install(single):
                identity = single.core[0]
                attempted.append(identity)
                if identity == "nestopia":
                    raise ValueError("Synthetic compiler failure")
                return {
                    "cores": [
                        {
                            "core_id": identity,
                            "approval_status": "operator_approved_installation",
                        }
                    ]
                }

            with patch.object(bootstrap, "install", side_effect=fake_install):
                result = bootstrap.install_fleet(args)
            self.assertEqual(attempted, ["sameboy", "nestopia", "mesen"])
            self.assertEqual(result["attempted"], 3)
            self.assertEqual(result["compiled"], 2)
            self.assertEqual(result["approved"], 2)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["failures"][0]["core_id"], "nestopia")
            self.assertEqual(result["status"], "incomplete")
            self.assertFalse(result["execution_checked"])

    def test_firmware_blocked_candidate_is_not_counted_as_approved(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(
                core=["mednafen_saturn"], install_root=Path(directory)
            )
            with patch.object(
                bootstrap,
                "install",
                return_value={
                    "cores": [
                        {
                            "core_id": "mednafen_saturn",
                            "approval_status": "candidate_firmware_missing",
                        }
                    ]
                },
            ):
                result = bootstrap.install_fleet(args)
            self.assertEqual(result["compiled"], 1)
            self.assertEqual(result["approved"], 0)
            self.assertEqual(result["candidate_unapproved"], 1)
            self.assertEqual(result["status"], "incomplete")

    def test_duplicate_core_selection_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(
                core=["sameboy", "sameboy"], install_root=Path(directory)
            )
            with self.assertRaises(ValueError):
                bootstrap.install_fleet(args)

    def test_cli_returns_nonzero_on_incomplete_fleet(self):
        with tempfile.TemporaryDirectory() as directory:
            result = {
                "status": "incomplete",
                "failed": 1,
                "approved": 0,
                "execution_checked": False,
            }
            output = io.StringIO()
            with patch.object(bootstrap, "install_fleet", return_value=result):
                with redirect_stdout(output):
                    code = bootstrap.main(
                        [
                            "--source-root", str(Path(directory) / "source"),
                            "--install-root", str(Path(directory) / "installed"),
                            "--fleet", "--core", "sameboy",
                        ]
                    )
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
