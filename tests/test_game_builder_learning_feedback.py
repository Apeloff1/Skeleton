"""Real adversarial promotion regressions: every missed gate remains actionable."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.competitive_mirror_training import TrainingCandidate, split_project
from skeleton.ai.game_builder.game_learning_feedback import (
    feedback_from_evaluation, feedback_from_cohort,
)
from skeleton.ai.game_builder.game_model_promotion import (
    PromotionError, PromotionEvaluation, PromotionStandard,
    evaluate_fresh_cohort,propose_progressive_standard,require_stronger_standard,
)


def evidence_rows():
    games = [sha256(f"new-independent-game-{i}".encode()).hexdigest()
             for i in range(2)]
    rows = []
    for game in games:
        for index in range(16):
            hostile = index % 2 == 0
            rows.append(TrainingCandidate(
                project_digest=game,
                split=split_project(game),
                example_id=canonical_digest({"game": game, "index": index}),
                instruction="Independently evaluate original game actions.",
                input=({"attack_family": f"rare_family_{index % 4}",
                        "replay_digest": game, "event_index": index}
                       if hostile else
                       {"canonical_witness": {"world": game, "event": index}}),
                expected={"decision": "reject" if hostile
                          else "accept_witnessed_incident_only"},
                evidence={"severity": 9 if hostile else 2,
                          "verified_control": not hostile},
            ))
    return tuple(rows)


def policy(bias=0):
    return dict(weights=[0.0] * 128, bias=bias,
                threshold=0.5, feature_spec="input_only_key_family_hash_128_v1")


def forgiving(**kwargs):
    return replace(PromotionStandard(), min_per_class=1,
                   min_balanced_accuracy=0, min_project_accuracy=0,
                   min_critical_recall=0, min_wilson_recall=0,
                   max_brier=1, **kwargs)


class AdversarialEvidencePromotionTests(unittest.TestCase):
    def test_complete_defect_accounting_without_leaking_heldout_sources(self):
        model = "a" * 64
        secret = "heldout_private_world_and_attack_identifier_123"
        defects = (
            "test:unhandled_attack_family:" + secret,
            "validation:reviewer_shortcut_detection",
            "test:high_severity_recall",
            "test:unhandled_attack_family:" + secret,
            "test:calibration_error",
        )
        evidence = PromotionEvaluation(
            model, "b" * 64, "c" * 64, {"private": secret},
            defects, None, "d" * 64,
        )
        ledger = feedback_from_evaluation(evidence, authorized=True)
        payload = ledger.payload()
        self.assertEqual(payload["blockers_accounted_for"], len(defects))
        self.assertEqual(sum(x["affected_gate_count"]
                             for x in payload["objectives"]), len(defects))
        self.assertEqual(payload["objectives"][0]["priority"], 100)
        self.assertEqual(payload["permitted_training_source"],
                         "new_source_reviewed_train_projects_only")
        self.assertFalse(payload["model_promotion_approved"])
        self.assertNotIn(secret, json.dumps(payload))
        self.assertEqual(ledger.digest, feedback_from_evaluation(
            evidence, authorized=True).digest)
        self.assertTrue(all(x["train_only"] and not x["complete"]
                            for x in payload["objectives"]))

    def test_passing_models_still_require_frontier_expansion(self):
        e = PromotionEvaluation("a"*64, "b"*64, "c"*64,
                                {}, (), None, "d"*64)
        p = feedback_from_evaluation(e, authorized=True).payload()
        self.assertTrue(p["quality_passed"])
        self.assertEqual(p["blockers_accounted_for"], 0)
        self.assertEqual(p["objectives"][0]["category"], "frontier_expansion")
        self.assertFalse(p["model_promotion_approved"])
        with self.assertRaises(PermissionError):
            feedback_from_evaluation(e, authorized=False)

    def test_stronger_standards_are_versioned_monotonic_and_not_installed(self):
        first = PromotionStandard()
        second = propose_progressive_standard(first,authorized=True)
        self.assertTrue(second.name.endswith("_v2"))
        self.assertGreater(second.min_train_projects,first.min_train_projects)
        self.assertGreater(second.min_per_class,first.min_per_class)
        self.assertGreaterEqual(second.min_counterfactual_accuracy,0.98)
        self.assertLess(second.max_brier,first.max_brier)
        require_stronger_standard(first,second)
        with self.assertRaises(PromotionError):
            require_stronger_standard(second,first)
        with self.assertRaises(PermissionError):
            propose_progressive_standard(first,authorized=False)
        third=propose_progressive_standard(second,authorized=True)
        require_stronger_standard(second,third)
        self.assertEqual(third.name,"game_review_progressive_2026_10_v3")
        self.assertEqual(first.name,"game_review_progressive_2026_10_v1")

    def test_mismatched_or_partial_cohort_evidence_is_rejected(self):
        with self.assertRaises(PromotionError):
            feedback_from_cohort({"schema": "wrong"}, mode="idle",
                                 authorized=True)
        with self.assertRaises(PromotionError):
            feedback_from_cohort({
                "schema": "skeleton.game_builder.fresh_cohort.v1",
                "blockers": ["live_critical_recall"], "passed": True,
                "candidate_digest": "a"*64,
            }, mode="usage", authorized=True)
        with self.assertRaises(PromotionError):
            feedback_from_cohort({
                "schema": "skeleton.game_builder.fresh_cohort.v1",
                "blockers": [], "passed": True,
                "candidate_digest": "a"*64,
            }, mode="background_unauthorized", authorized=True)

    def test_live_family_coverage_and_missed_hazards_are_vetoes(self):
        rows=evidence_rows()
        result=evaluate_fresh_cohort(
            rows, policy(bias=-2),standard=forgiving(min_family_cases=9),
            source_projects=(),authorized=True)
        self.assertFalse(result["passed"])
        self.assertEqual(result["candidate_digest"], canonical_digest(policy(-2)))
        self.assertTrue(any(x.startswith("live_family_coverage:")
                            for x in result["blockers"]))
        self.assertTrue(any(x.startswith("live_missed_attack_family:")
                            for x in result["blockers"]))
        ledger=feedback_from_cohort(result,mode="usage",authorized=True)
        self.assertEqual(ledger.phase,"usage")
        self.assertEqual(ledger.blocker_count,len(result["blockers"]))
        self.assertFalse(ledger.quality_passed)
        self.assertEqual(ledger.digest,feedback_from_cohort(
            result,mode="usage",authorized=True).digest)

    def test_no_live_model_can_hide_regressions_behind_global_averages(self):
        result=evaluate_fresh_cohort(
            evidence_rows(),policy(bias=-2),
            standard=forgiving(min_family_cases=1),
            source_projects=(),authorized=True,champion=policy(bias=2))
        self.assertEqual(result["champion_comparison"]["candidate_champion_digest"],
                         canonical_digest(policy(bias=2)))
        self.assertTrue(any(x.startswith("live_champion_adversarial_regression:")
                            for x in result["blockers"]))

    def test_strict_live_shortcut_gate_is_evaluated_without_training(self):
        result=evaluate_fresh_cohort(
            evidence_rows(),policy(),
            standard=forgiving(min_family_cases=1,
                               min_counterfactual_accuracy=0.98),
            source_projects=(),authorized=True)
        self.assertIn("live_counterfactual_shortcut_detection",result["blockers"])
        self.assertGreater(result["counterfactual"]["attempted"],50)
        self.assertFalse(result["counterfactual"]["training_performed"])
        self.assertFalse(result["heldout_observations_used_for_training"])

    def test_project_reuse_and_unauthorized_review_fail_closed(self):
        rows=evidence_rows()
        with self.assertRaises(PromotionError):
            evaluate_fresh_cohort(rows,policy(),standard=forgiving(),
                                  source_projects=(rows[0].project_digest,),
                                  authorized=True)
        with self.assertRaises(PermissionError):
            evaluate_fresh_cohort(rows,policy(),standard=forgiving(),
                                  source_projects=(),authorized=False)


if __name__=="__main__":
    unittest.main()
