"""Contract checks for human-only game-design review gate, never a game quality claim."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from skeleton.ai.training.jeeves_game_design_review_gate import (
    ASSESSMENT_SCHEMA, CRITERIA, adjudicate, prepare,
)
from skeleton.ai.training.jeeves_game_design_review_cli import blank_assessment
from skeleton.ai.training.jeeves_production_game_train import ProductionCheckpointError


class GameReviewGateTests(unittest.TestCase):
    @staticmethod
    def _benchmark(path: Path) -> None:
        entries = [
            {
                "family": ("mechanics", "narrative", "npc", "world",
                           "economy", "tooling", "accessibility", "review")[i // 3],
                "prompt": f"Original held-out design situation #{i}",
                "parent_output": f"baseline answer {i}",
                "candidate_output": f"candidate answer {i}",
            }
            for i in range(24)
        ]
        path.write_text(json.dumps({
            "schema_version": "skeleton.jeeves.game_design_answer_benchmark.v1",
            "status": "needs_independent_game_design_review",
            "parent_checkpoint_sha256": "a" * 64,
            "candidate_checkpoint_sha256": "b" * 64,
            "results": entries,
        }), encoding="utf-8")

    @staticmethod
    def _completed_review(packet: Path, mapping: Path, reviewer: str,
                          target: Path, *, strong: bool, critical: bool = False) -> None:
        blank_assessment(packet, reviewer, target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        key = json.loads(mapping.read_text(encoding="utf-8"))
        for row in payload["ratings"]:
            c = key["candidate_label_by_item"][row["item_id"]]
            parent = dict.fromkeys(CRITERIA, 1)
            candidate = dict.fromkeys(CRITERIA, 3 if strong else 0)
            row["scores_a"] = candidate if c == "A" else parent
            row["scores_b"] = candidate if c == "B" else parent
            row["critical_a"] = critical if c == "A" else False
            row["critical_b"] = critical if c == "B" else False
            row["evidence_note"] = "Manual test fixture: rubric values are arbitrary, never real review."
        payload["human_review_complete"] = True
        target.write_text(json.dumps(payload), encoding="utf-8")

    def test_forms_contain_no_fabricated_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, packet, key = (root / name for name in ("src.json", "packet.json", "key.json"))
            self._benchmark(source)
            result = prepare(source_report=source, public_packet=packet, private_key=key)
            self.assertEqual(result["generation_count"], 24)
            form = root / "review.json"
            summary = blank_assessment(packet, "reviewer-one", form)
            self.assertEqual(summary["scores_entered"], 0)
            scores = json.loads(form.read_text(encoding="utf-8"))["ratings"]
            self.assertEqual(len(scores), 24)
            self.assertTrue(all(all(v is None for v in row["scores_a"].values()) for row in scores))

    def test_only_complete_distinct_reviews_can_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, packet, key = (root / name for name in ("src.json", "packet.json", "key.json"))
            a, b = root / "a.json", root / "b.json"
            self._benchmark(source)
            prepare(source_report=source, public_packet=packet, private_key=key)
            blank_assessment(packet, "reviewer-one", a)
            blank_assessment(packet, "reviewer-two", b)
            with self.assertRaisesRegex(ProductionCheckpointError, "integer"):
                adjudicate(packet_path=packet, private_key_path=key, assessment_paths=(a, b))
            self._completed_review(packet, key, "reviewer-one", root / "c.json", strong=True)
            self._completed_review(packet, key, "reviewer-two", root / "d.json", strong=True)
            passed = adjudicate(
                packet_path=packet, private_key_path=key,
                assessment_paths=(root / "c.json", root / "d.json"),
            )
            self.assertEqual(passed["status"], "eligible_for_separate_promotion_review")
            self.assertFalse(passed["candidate_promoted"])
            self.assertEqual(passed["fully_reviewed_pairs"], 24)
            with self.assertRaisesRegex(ProductionCheckpointError, "distinct"):
                adjudicate(packet_path=packet, private_key_path=key,
                           assessment_paths=(root / "c.json", root / "c.json"))

    def test_worse_candidate_and_critical_defects_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, packet, key = (root / name for name in ("src.json", "packet.json", "key.json"))
            self._benchmark(source)
            prepare(source_report=source, public_packet=packet, private_key=key)
            a, b = root / "a.json", root / "b.json"
            self._completed_review(packet, key, "reviewer-one", a, strong=False)
            self._completed_review(packet, key, "reviewer-two", b, strong=False)
            rejected = adjudicate(packet_path=packet, private_key_path=key, assessment_paths=(a, b))
            self.assertEqual(rejected["status"], "quality_gate_failed")
            self.assertFalse(rejected["game_design_quality_gate_passed"])
            c, d = root / "c.json", root / "d.json"
            self._completed_review(packet, key, "reviewer-three", c, strong=True, critical=True)
            self._completed_review(packet, key, "reviewer-four", d, strong=True)
            rejected = adjudicate(packet_path=packet, private_key_path=key, assessment_paths=(c, d))
            self.assertEqual(rejected["status"], "quality_gate_failed")
            self.assertGreater(len(rejected["candidate_critical_defects"]), 0)

    def test_packet_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, packet, key = (root / name for name in ("src.json", "packet.json", "key.json"))
            self._benchmark(source)
            prepare(source_report=source, public_packet=packet, private_key=key)
            a, b = root / "a.json", root / "b.json"
            self._completed_review(packet, key, "reviewer-one", a, strong=True)
            self._completed_review(packet, key, "reviewer-two", b, strong=True)
            packet.write_text(packet.read_text(encoding="utf-8") + " ", encoding="utf-8")
            with self.assertRaisesRegex(ProductionCheckpointError, "packet differs"):
                adjudicate(packet_path=packet, private_key_path=key, assessment_paths=(a, b))


if __name__ == "__main__":
    unittest.main()
