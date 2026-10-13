"""Adversarial metadata-invariance, heldout integrity and progressive standards."""
from __future__ import annotations

from dataclasses import replace
import unittest

from skeleton.ai.game_builder.game_training_flow import (
    plan_training_flow,train_isolated_review_ranker,
)
from skeleton.ai.game_builder.game_model_promotion import (
    PromotionStandard,PromotionError,
    evaluate_candidate,require_stronger_standard,
)
from skeleton.ai.game_builder.game_learning_challenges import (
    challenge_reviewer,challenging_train_examples,
)
from tests.test_game_builder_reviewer_promotion import promotion_corpus


class AdversarialReviewerQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=plan_training_flow(promotion_corpus(),authorized=True)
        cls.fit=train_isolated_review_ranker(cls.plan,epochs=75,authorized=True)
        cls.policy=cls.fit["symbolic_policy"]

    def test_hard_redteam_metadata_spoofing_exposes_simplistic_model(self):
        heldout=tuple(x for x in self.plan.selected if x.split=="validation")
        audit=challenge_reviewer(heldout,self.policy,authorized=True)
        self.assertGreater(audit.attempted,60)
        self.assertEqual(audit.attempted,len(heldout)*4)
        self.assertGreater(len(audit.by_family),4)
        self.assertTrue(audit.heldout)
        self.assertGreater(len(audit.failed),0,
                           "metadata-only reviewer should not falsely appear fully robust")
        self.assertLess(audit.accuracy,1.0)
        self.assertEqual(audit.digest,challenge_reviewer(
            heldout,self.policy,authorized=True).digest)
        self.assertEqual(audit.payload()["learned_model_weights_mutated"],False)
        self.assertTrue(audit.payload()["heldout_test_cases_not_retrained"])
        with self.assertRaises(PromotionError):
            challenging_train_examples(heldout,audit,authorized=True)

    def test_failed_train_only_variants_have_exact_source_receipts(self):
        original=tuple(x for x in self.plan.selected if x.split=="train")
        audit=challenge_reviewer(original,self.policy,authorized=True)
        cases=challenging_train_examples(original,audit,authorized=True)
        self.assertEqual(len(cases),len(audit.failed))
        self.assertTrue(all(x.split=="train" for x in cases))
        self.assertEqual(len({x.example_id for x in cases}),len(cases))
        self.assertTrue(all("challenge_report_digest" in x.evidence for x in cases))
        self.assertTrue(all(x.evidence["challenge_report_digest"]==audit.digest
                            for x in cases))
        self.assertTrue(all(x.approval=="quarantined" for x in cases))
        self.assertEqual(cases,challenging_train_examples(
            original,audit,authorized=True))

    def test_new_higher_bar_is_monotonic_and_blocks_shortcut_models(self):
        original=PromotionStandard()
        stronger=replace(original,min_counterfactual_accuracy=0.995)
        require_stronger_standard(original,stronger)
        with self.assertRaises(PromotionError):
            require_stronger_standard(stronger,original)
        baseline=evaluate_candidate(self.plan,self.fit,
                                     standard=original,authorized=True)
        strict=evaluate_candidate(self.plan,self.fit,
                                   standard=stronger,authorized=True)
        self.assertTrue(baseline.passed,str(baseline.blockers))
        self.assertFalse(strict.passed,
                         "do not promote a model that learns labels from attack markers")
        self.assertIn("validation:reviewer_shortcut_detection",strict.blockers)
        self.assertIn("metamorphic_validation",strict.metrics)
        self.assertIn("metamorphic_test",strict.metrics)

    def test_spoofed_split_and_repeated_sources_are_rejected(self):
        original=tuple(x for x in self.plan.selected if x.split=="train")
        with self.assertRaises(PromotionError):
            challenge_reviewer((original[0],original[0]),self.policy,
                               authorized=True)
        with self.assertRaises(PermissionError):
            challenge_reviewer(original,self.policy,authorized=False)
        mixed=(original[0],next(x for x in self.plan.selected if x.split=="test"))
        with self.assertRaises(PromotionError):
            challenge_reviewer(mixed,self.policy,authorized=True)


if __name__=="__main__":
    unittest.main()
