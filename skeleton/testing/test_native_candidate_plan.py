"""Non-escalating native SGD plan and explicit owner approval."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.plan import TrainingPlan
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected

A="a"*64
B="b"*64


class TestCandidatePlan(unittest.TestCase):
    def test_candidate_plan_has_finite_digest(self):
        plan=TrainingPlan("run_1",A,B,operator_approved=True)
        self.assertEqual(plan.output_kind,"candidate-only")
        self.assertEqual(len(plan.digest),64)

    def test_no_unapproved_training(self):
        with self.assertRaises(CandidateRejected):
            TrainingPlan("run_1",A,B)

    def test_never_direct_to_production(self):
        with self.assertRaises(CandidateRejected):
            TrainingPlan("run_1",A,B,operator_approved=True,output_kind="production")

    def test_boolean_not_optimizer_steps(self):
        with self.assertRaises(CandidateRejected):
            TrainingPlan("run_1",A,B,operator_approved=True,max_optimizer_steps=True)

    def test_changed_learning_rate_changes_identity(self):
        plan=TrainingPlan("run_1",A,B,operator_approved=True)
        self.assertNotEqual(plan.digest,replace(plan,learning_rate_ppm=5000).digest)

    def test_very_large_step_budget_denied(self):
        with self.assertRaises(CandidateRejected):
            TrainingPlan("run_1",A,B,operator_approved=True,max_optimizer_steps=1000001)


if __name__ == "__main__":
    unittest.main()
