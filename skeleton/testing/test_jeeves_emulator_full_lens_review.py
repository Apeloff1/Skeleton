"""Regression contract for catalog-wide emulator receipts -> Jeeves/Dragon lens triage.

Synthetic fixtures verify structural safeguards, NOT genuine native gameplay
or actual Jeeves checkpoint parameter gain.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from skeleton.jeeves.game_learning import _digest
from skeleton.jeeves.agent.lens_system import LensCatalog
from skeleton.jeeves.game_emulator_training_lab import SCHEMA as TRAINING_SCHEMA
from skeleton.jeeves.game_emulator_lens_review import (
    EmulatorLensReviewError,
    complete_lens_registry,
    review_verified_training_report,
    validate_training_receipts,
)
from skeleton.jeeves.game_learning_cli import main


def _synthetic_report(runs: int = 4) -> dict:
    receipts = []
    for index in range(runs):
        entry = {
            "trace_digest": _digest(["fictional_fixture_only", index]),
            "scrutiny_checks": {f"source_check_{k}": True for k in range(10)},
            "actual_steps": 3,
            "actual_replay_steps": 6,
            "actual_tabular_q_updates": 3,
            "training_commit": True,
        }
        entry["receipt_digest"] = _digest(entry)
        receipts.append(entry)
    report = {
        "schema_version": TRAINING_SCHEMA,
        "source_lineage": {"rights_acknowledged": True, "fixture_not_a_real_emulator": True},
        "run_count": runs,
        "audited_run_receipts": receipts,
        "actual_training_steps": 3 * runs,
        "actual_q_table_updates": 3 * runs,
        "actual_neural_parameter_updates": 0,
        "policy_snapshot": {"snapshot_digest": _digest("fixture_policy")},
        "adaptive_evidence_curriculum": {"fixture": True},
        "heldout_evaluation": {"fixture": True},
    }
    report["report_digest"] = _digest(report)
    return report


def _reseal(report: dict) -> None:
    report["report_digest"] = _digest({k: v for k, v in report.items() if k != "report_digest"})


class AllLensReviewContract(unittest.TestCase):
    def test_all_registered_lenses_get_one_typed_replay_dragon_adversary_task(self):
        report = _synthetic_report()
        first = review_verified_training_report(report)
        self.assertGreaterEqual(first["catalog_lens_count"], 200)
        self.assertEqual(first["catalog_lens_count"],
                         len(complete_lens_registry().all()) + len(LensCatalog().all()))
        expected = {spec.key for spec in complete_lens_registry().all()}
        expected |= {"routing/" + spec.lens_id for spec in LensCatalog().all()}
        seen = set()
        page = first
        while True:
            for row in page["reviews"]:
                self.assertNotIn(row["lens_key"], seen)
                seen.add(row["lens_key"])
                self.assertEqual(row["source_report_digest"], report["report_digest"])
                self.assertFalse(row["evidence_triangulation_complete"])
                self.assertFalse(row["semantic_interpretation_asserted"])
                self.assertIn("awaiting_independent", row["dragon_observation"]["status"])
                self.assertIn("awaiting_independent", row["adversarial_review"]["status"])
                self.assertEqual(row["ai_gradient_updates_by_review"], 0)
                self.assertTrue(row["source_receipt_digests"])
            offset = page["next_offset"]
            if offset is None:
                break
            page = review_verified_training_report(report, offset=offset)
        self.assertEqual(seen, expected)
        self.assertFalse(first["production_model_promotion_authorized"])
        self.assertEqual(first["actual_neural_parameter_updates_by_review"], 0)

    def test_page_stable_digest_source_and_catalog_unchanged(self):
        report = _synthetic_report()
        a = review_verified_training_report(report, offset=20, limit=13)
        b = review_verified_training_report(copy.deepcopy(report), offset=20, limit=13)
        self.assertEqual(a, b)
        self.assertEqual(a["page_size"], 13)
        self.assertEqual(a["next_offset"], 33)
        self.assertNotEqual(a["review_digest"], review_verified_training_report(
            report, offset=0, limit=13,
        )["review_digest"])

    def test_sparse_runs_are_review_questions_not_validated_interpretations(self):
        review = review_verified_training_report(_synthetic_report(1), limit=512)
        self.assertGreater(review["catalog_lens_count"], review["review_material_ready_count"])
        self.assertTrue(any(not x["review_material_ready"] for x in review["reviews"]))
        self.assertTrue(all(not x["evidence_triangulation_complete"] for x in review["reviews"]))

    def test_tampered_report_and_one_run_fails_closed(self):
        report = _synthetic_report()
        report["audited_run_receipts"][0]["actual_steps"] = 2
        with self.assertRaises(EmulatorLensReviewError):
            review_verified_training_report(report)
        _reseal(report)
        with self.assertRaises(EmulatorLensReviewError):
            review_verified_training_report(report)

    def test_no_rights_or_fake_scrutiny_or_duplicate_traces(self):
        for change in ("rights", "scrutiny", "duplicate", "weights", "wrong_count"):
            with self.subTest(change=change):
                report = _synthetic_report()
                if change == "rights":
                    report["source_lineage"]["rights_acknowledged"] = False
                elif change == "scrutiny":
                    report["audited_run_receipts"][0]["scrutiny_checks"]["source_check_1"] = False
                    receipt = report["audited_run_receipts"][0]
                    receipt["receipt_digest"] = _digest({
                        k: v for k, v in receipt.items() if k != "receipt_digest"
                    })
                elif change == "duplicate":
                    receipt = report["audited_run_receipts"][1]
                    receipt["trace_digest"] = report["audited_run_receipts"][0]["trace_digest"]
                    receipt["receipt_digest"] = _digest({
                        k: v for k, v in receipt.items() if k != "receipt_digest"
                    })
                elif change == "weights":
                    report["actual_neural_parameter_updates"] = 1
                else:
                    report["run_count"] = 5
                _reseal(report)
                with self.assertRaises(EmulatorLensReviewError):
                    validate_training_receipts(report)

    def test_bounds_and_empty_page(self):
        report = _synthetic_report()
        for options in ({"offset": -1}, {"limit": 0}, {"limit": 513},
                        {"offset": True}, {"limit": True}):
            with self.subTest(options=options):
                with self.assertRaises(EmulatorLensReviewError):
                    review_verified_training_report(report, **options)
        beyond = review_verified_training_report(report, offset=10000, limit=10)
        self.assertEqual(beyond["review_lens_count"], 0)
        self.assertIsNone(beyond["next_offset"])

    def test_canonical_cli_recombines_split_policy_evidence_and_private_output(self):
        report = _synthetic_report()
        policy = report.pop("policy_snapshot")
        evidence = dict(report)
        evidence["policy_snapshot_digest"] = policy["snapshot_digest"]
        evidence["evidence_digest"] = hashlib.sha256(
            json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False).encode("utf-8")
        ).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy_path = root / "policy.json"
            evidence_path = root / "evidence.json"
            review_path = root / "review.json"
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            args = [
                "review-emulator-lenses",
                "--policy-file", str(policy_path),
                "--evidence-file", str(evidence_path),
                "--lens-review-file", str(review_path),
                "--limit", "17",
            ]
            with redirect_stdout(StringIO()):
                self.assertEqual(main(args), 0)
            value = json.loads(review_path.read_text(encoding="utf-8"))
            self.assertEqual(value["review_lens_count"], 17)
            self.assertFalse(value["source_integrity"]["operator_report_authenticated"])
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(review_path.stat().st_mode), 0o600)
            with redirect_stderr(StringIO()):
                self.assertEqual(main(args), 2)
            evidence["evidence_digest"] = "0" * 64
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            review_path.unlink()
            with redirect_stderr(StringIO()):
                self.assertEqual(main(args), 2)
            self.assertFalse(review_path.exists())


if __name__ == "__main__":
    unittest.main()
