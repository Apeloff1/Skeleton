"""Opt-in native original-game E2E suite runner: no CI triggers or fake victories."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_specialized_e2e_runner import (
    SpecializedTestError, SUITE_ID, _execute, _registered_suite,
    run_registered_native_e2e,
)


class NativeSuiteOperatorEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.project = self.base / "original_repo"
        (self.project / "machine").mkdir(parents=True)
        (self.project / "skeleton/ai/game_builder").mkdir(parents=True)
        (self.project / "tests").mkdir()
        self.script = "tests/test_studio_source_demo.py"
        self.implementation = "skeleton/ai/game_builder/source_demo.py"
        (self.project / self.script).write_text(
            "def test_original_game():\n    assert 1 == 1\n", encoding="utf-8",
        )
        (self.project / self.implementation).write_text(
            "ORIGINAL = True\n", encoding="utf-8",
        )
        self.manifest = self.project / "machine/e2e_suites.json"
        self.suite = {
            "id": SUITE_ID, "tier": "offline",
            "cwd": ".", "timeout_seconds": 1200,
            "required_files": [self.script, self.implementation],
            "command": [
                "python", "-m", "pytest", "-q", "-ra",
                "--tb=short", "--noconftest", self.script,
            ],
        }
        self.write_manifest()
        self.receipt = self.base / "native-test-receipt.json"

    def write_manifest(self):
        self.manifest.write_text(
            json.dumps({"version": 1, "suites": [self.suite]}),
            encoding="utf-8",
        )

    def test_authorized_valid_suite_receipt_is_digest_bound_but_not_release(self):
        with patch(
            "skeleton.ai.game_builder.studio_specialized_e2e_runner._execute",
            return_value=("passed", 0, 248, 0),
        ) as runner:
            receipt = run_registered_native_e2e(
                self.project, authorized=True, execute=True,
                receipt_path=self.receipt,
            )
        runner.assert_called_once()
        self.assertEqual(receipt["selected_test_files"], 1)
        self.assertEqual(receipt["registered_source_files"], 2)
        self.assertTrue(receipt["source_contract_tests_passed"])
        self.assertFalse(receipt["source_changed_during_execution"])
        self.assertFalse(receipt["genuine_rom_emulator_execution_proven"])
        self.assertFalse(receipt["hardware_audio_video_qualified"])
        self.assertFalse(receipt["release_approved"])
        self.assertEqual(json.loads(self.receipt.read_text()), receipt)
        from skeleton.ai.game_builder.contracts import canonical_digest
        self.assertEqual(
            receipt["receipt_digest"],
            canonical_digest({
                key: value for key, value in receipt.items()
                if key != "receipt_digest"
            }),
        )
        with self.assertRaises(SpecializedTestError):
            run_registered_native_e2e(
                self.project, authorized=True, execute=True,
                receipt_path=self.receipt,
            )

    def test_authorization_flags_cannot_be_bypassed_by_a_mocked_pass(self):
        with patch(
            "skeleton.ai.game_builder.studio_specialized_e2e_runner._execute"
        ) as runner:
            for auth, run in ((False, True), (True, False), (False, False)):
                with self.subTest(auth=auth, run=run):
                    with self.assertRaises(PermissionError):
                        run_registered_native_e2e(
                            self.project, authorized=auth, execute=run,
                            receipt_path=self.receipt,
                        )
            runner.assert_not_called()

    def test_registry_cannot_select_commands_outside_approved_local_tests(self):
        variants = [
            ["python", "-m", "pytest", "-q", "-ra", "--tb=short",
             "--noconftest", "../outside.py"],
            ["python", "-m", "pytest", "-q", "-ra", "--tb=short",
             "--noconftest", self.script, "-k", "autostart"],
            ["bash", "-c", "curl remote"],
            ["python", "-m", "pytest", "-q", "-ra", "--tb=short",
             "--noconftest", self.script, self.script],
        ]
        for command in variants:
            with self.subTest(command=command):
                self.suite["command"] = command
                self.write_manifest()
                with self.assertRaises(SpecializedTestError):
                    _registered_suite(self.project)
        self.suite["command"] = [
            "python", "-m", "pytest", "-q", "-ra",
            "--tb=short", "--noconftest", self.script,
        ]
        self.write_manifest()
        self.assertEqual(_registered_suite(self.project)[0], (self.script,))

    def test_tampered_or_symlinked_input_never_admitted(self):
        self.suite["required_files"] = [self.script, "../../outside.py"]
        self.write_manifest()
        with self.assertRaises(SpecializedTestError):
            _registered_suite(self.project)
        self.suite["required_files"] = [self.script, self.implementation]
        self.write_manifest()
        original = self.project / self.implementation
        original.unlink()
        try:
            original.symlink_to(self.project / self.script)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation disabled on host")
        with self.assertRaises(SpecializedTestError):
            _registered_suite(self.project)

    def test_source_change_during_test_disallows_passed_claim(self):
        def simulated_run(repo_root, chosen, timeout, logs):
            (self.project / self.implementation).write_text("FORGED = True\n")
            return "passed", 0, 75, 0
        with patch(
            "skeleton.ai.game_builder.studio_specialized_e2e_runner._execute",
            side_effect=simulated_run,
        ):
            output = run_registered_native_e2e(
                self.project, authorized=True, execute=True,
                receipt_path=self.receipt,
            )
        self.assertEqual(output["process_status"], "passed")
        self.assertTrue(output["source_changed_during_execution"])
        self.assertFalse(output["source_contract_tests_passed"])

    def test_failed_test_or_timed_out_test_never_passes(self):
        for status, exit_code in (("failed", 1), ("timeout", None),
                                  ("not_started", None)):
            with self.subTest(status=status):
                destination = self.base / f"{status}.json"
                with patch(
                    "skeleton.ai.game_builder.studio_specialized_e2e_runner._execute",
                    return_value=(status, exit_code, 123, 456),
                ):
                    output = run_registered_native_e2e(
                        self.project, authorized=True, execute=True,
                        receipt_path=destination,
                    )
                self.assertFalse(output["source_contract_tests_passed"])
                self.assertFalse(output["genuine_rom_emulator_execution_proven"])

    def test_optional_runner_executes_only_the_fixed_pytest_arguments(self):
        with TemporaryDirectory() as temp:
            work = Path(temp)
            with patch(
                "skeleton.ai.game_builder.studio_specialized_e2e_runner.subprocess.run",
                return_value=subprocess.CompletedProcess(
                    ["python", "-m", "pytest"], 0,
                ),
            ) as invoke:
                status = _execute(
                    self.project, (self.script,), 40, work,
                )
        args, kw = invoke.call_args
        self.assertEqual(args[0][1:7], [
            "-m", "pytest", "-q", "-ra", "--tb=short", "--noconftest",
        ])
        self.assertEqual(args[0][-1], self.script)
        self.assertIs(kw["shell"], False)
        self.assertIs(kw["check"], False)
        self.assertEqual(kw["timeout"], 40)
        self.assertEqual(status[:2], ("passed", 0))


if __name__ == "__main__":
    unittest.main()
