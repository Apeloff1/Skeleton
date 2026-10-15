"""Fail-closed suite receipt tests; no native core, external ROM, network or CI.

These focused cases exercise custody of *written bytes*, cancellation, and
missing-source status. Source-executed original ROM tests live separately in
test_game_original_rom_ai_acceptance and test_game_original_rom_goal_training.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_game_rom_acceptance_suite import (
    AcceptanceSuiteError,
    _canonical, _json_file, _run, _sha,
    _verify_digest, run_acceptance_suite,
)


class AcceptanceSuiteCustodyTests(unittest.TestCase):
    def test_digest_fails_on_rehashed_or_missing_inner_receipt(self):
        payload = {"schema_version": "fixture", "evidence": {"passed": True}}
        payload["receipt_digest"] = _sha(_canonical(payload))
        _verify_digest(payload, "receipt_digest")
        payload["evidence"]["passed"] = False
        with self.assertRaises(AcceptanceSuiteError):
            _verify_digest(payload, "receipt_digest")

    def test_json_reader_rejects_invalid_and_non_regular_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            good = base / "measured.json"
            good.write_text(json.dumps({"real_step": 1}), encoding="utf-8")
            parsed, proof = _json_file(good)
            self.assertEqual(parsed["real_step"], 1)
            self.assertEqual(proof["bytes"], good.stat().st_size)
            self.assertEqual(proof["sha256"], _sha(good.read_bytes()))
            alias = base / "alias.json"
            alias.symlink_to(good)
            with self.assertRaises(AcceptanceSuiteError):
                _json_file(alias)
            blank = base / "blank.json"
            blank.write_bytes(b"")
            with self.assertRaises(AcceptanceSuiteError):
                _json_file(blank)

    def test_nonzero_child_fails_without_fake_success_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("subprocess.run", return_value=subprocess.CompletedProcess(
                args=["python", "-m", "fixture"], returncode=3,
                stdout="fake pass", stderr="real runtime failed",
            )):
                with self.assertRaises(AcceptanceSuiteError):
                    _run(["python", "-m", "fixture"], Path(folder),
                         "offline_source", seconds=30)

    def test_real_worker_timeout_is_not_a_completed_job(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(
                cmd="python fixture", timeout=30,
            )):
                with self.assertRaises(AcceptanceSuiteError):
                    _run(["python", "-m", "fixture"], Path(folder),
                         "timeout_source", seconds=30)

    def test_no_test_shortcut_still_requires_real_original_pipeline(self):
        with tempfile.TemporaryDirectory() as folder:
            private = Path(folder) / "new-original-acceptance"
            with patch(
                "scripts.run_game_rom_acceptance_suite._run",
                side_effect=AcceptanceSuiteError("first source CPU boot failed"),
            ):
                with self.assertRaises(AcceptanceSuiteError):
                    run_acceptance_suite(private, seed=13, tests=False)
            self.assertTrue(private.exists())
            self.assertFalse((private / "suite-acceptance.json").exists())

    def test_instruction_microtrace_receipts_reject_rehashed_tampered_samples(self):
        from skeleton.jeeves.game_rom_instruction_divergence import (
            InstructionDivergenceConfig, compare_original_rom_instruction_branches,
        )
        from scripts.run_game_rom_acceptance_suite import _verify_instruction_microtrace
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            result = compare_original_rom_instruction_branches(
                InstructionDivergenceConfig(
                    seed=9, instruction_count=64, sample_stride=4,
                    max_cycles_per_branch=4096,
                    action_subset=("idle", "a"),
                ),
            )
            path = base / "original-cpu-instruction-divergence.json"
            path.write_bytes(_canonical(result) + b"\n")
            self.assertTrue(_verify_instruction_microtrace(base)["accepted"])
            result["actual_passive_and_controller_interventions"][1][
                "first_run"]["time_and_video_evidence"][0][
                    "real_div_timer_interrupts"]["tima"] = 17
            # Even if the caller rehashes the outer report, each original
            # hardware sample must independently match its source digest.
            result["report_digest"] = _sha(_canonical({
                key: value for key, value in result.items() if key != "report_digest"
            }))
            path.write_bytes(_canonical(result) + b"\n")
            with self.assertRaises(AcceptanceSuiteError):
                _verify_instruction_microtrace(base)

    def test_existing_destination_rejected_without_overwriting(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(AcceptanceSuiteError):
                run_acceptance_suite(Path(folder), tests=False)

    def test_finite_worker_and_seed_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for index, settings in enumerate([
                {"seed": -1}, {"seed": 2**63}, {"process_timeout_seconds": 20},
                {"process_timeout_seconds": 100000},
            ]):
                with self.subTest(settings=settings):
                    with self.assertRaises(AcceptanceSuiteError):
                        run_acceptance_suite(base / f"bad-{index}", tests=False, **settings)


if __name__ == "__main__":
    unittest.main()
