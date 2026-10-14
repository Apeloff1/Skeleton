"""Actual v2 normalized model training beats attack-label shortcuts on heldout worlds."""
from __future__ import annotations

import unittest

from skeleton.ai.game_builder.game_model_promotion import (
    PromotionStandard,evaluate_candidate,predict_review,
)
from skeleton.ai.game_builder.game_training_flow import (
    plan_training_flow,train_isolated_review_ranker,
)
from skeleton.ai.game_builder.game_reviewer_v2 import (
    FEATURE_SPEC,evidence_features,train_robust_game_reviewer,
)
from skeleton.ai.game_builder.game_learning_challenges import challenge_reviewer
from tests.test_game_builder_reviewer_promotion import promotion_corpus


class RobustReviewerModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=plan_training_flow(promotion_corpus(),authorized=True)
        cls.basic=train_isolated_review_ranker(cls.plan,epochs=75,
                                                 authorized=True)
        cls.robust=train_robust_game_reviewer(cls.plan,epochs=75,
                                               authorized=True)

    def test_trains_a_genuine_normalized_256_weight_policy(self):
        fit=self.robust
        self.assertTrue(fit["training_performed"])
        self.assertEqual(fit["status"],"experimental_fit_only")
        self.assertEqual(fit["symbolic_policy"]["feature_spec"],FEATURE_SPEC)
        self.assertEqual(len(fit["symbolic_policy"]["weights"]),256)
        self.assertGreater(fit["train_augmented_examples"],
                           fit["example_counts"]["train"]*3)
        self.assertFalse(fit["production_dragon_or_jeeves_weights_changed"])
        self.assertGreaterEqual(fit["validation_metamorphic"]["balanced_accuracy"],0.94)
        self.assertGreaterEqual(fit["test_metamorphic"]["balanced_accuracy"],0.94)

    def test_v2_is_strong_on_same_independent_challenge_as_v1(self):
        heldout=tuple(x for x in self.plan.selected if x.split=="test")
        before=challenge_reviewer(
            heldout,self.basic["symbolic_policy"],authorized=True)
        after=challenge_reviewer(
            heldout,self.robust["symbolic_policy"],authorized=True)
        self.assertLess(before.accuracy,0.98)
        self.assertGreaterEqual(after.accuracy,0.98)
        self.assertGreater(after.accuracy,before.accuracy)
        self.assertEqual(len(after.failed),0)
        self.assertEqual(after.policy_digest,self.robust["fitted_policy_digest"])
        self.assertEqual(after.digest,challenge_reviewer(
            heldout,self.robust["symbolic_policy"],authorized=True).digest)

    def test_strict_increasing_quality_standard_distinguishes_models(self):
        strict=PromotionStandard(min_counterfactual_accuracy=0.98)
        rejected=evaluate_candidate(
            self.plan,self.basic,standard=strict,authorized=True)
        certified=evaluate_candidate(
            self.plan,self.robust,standard=strict,authorized=True)
        self.assertFalse(rejected.passed)
        self.assertTrue(certified.passed,str(certified.blockers))
        self.assertIn("validation:reviewer_shortcut_detection",
                      rejected.blockers)
        self.assertEqual(certified.metrics["metamorphic_test"]["failed"],0)
        self.assertGreater(certified.metrics["test"]["critical_cases"],10)
        self.assertEqual(certified.metrics["test"]["critical_recall"],1.0)
        self.assertEqual(certified.candidate_digest,
                         self.robust["fitted_policy_digest"])

    def test_source_envelope_changes_do_not_alter_v2_decisions(self):
        heldout=tuple(x for x in self.plan.selected if x.split=="validation")
        from dataclasses import replace
        for example in heldout[:24]:
            original=predict_review(example,self.robust["symbolic_policy"])
            wrapped=replace(example,input={
                "evidence_bundle":{"raw_gameplay":example.input},
                "representation":"source_preserving_envelope_v1",
            })
            new=predict_review(wrapped,self.robust["symbolic_policy"])
            self.assertEqual(original["predicted_reject"],
                             new["predicted_reject"])
            self.assertEqual(original["probability"],new["probability"])
        self.assertEqual(self.robust["fitted_policy_digest"],
                         train_robust_game_reviewer(
                             self.plan,epochs=75,authorized=True)["fitted_policy_digest"])

if __name__=="__main__":
    unittest.main()
