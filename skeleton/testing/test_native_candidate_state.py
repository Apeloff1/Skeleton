"""Finite forward-only training state and fail-closed recovery rules."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.state_rules import RunState
from skeleton.ai.runtime.operational_ai.native_candidate.recovery import decide
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected


class TestCandidateRunState(unittest.TestCase):
    def test_forward_lifecycle(self):
        status=RunState("run_1","new")
        status=status.advance("verified")
        status=status.advance("training")
        status=status.advance("candidate")
        self.assertEqual(status.revision,3)

    def test_uncertain_cannot_resume_training(self):
        held=RunState("run_1","uncertain")
        with self.assertRaises(CandidateRejected):
            held.advance("training")
        self.assertFalse(decide(held).retry_authorized)

    def test_held_is_terminal(self):
        with self.assertRaises(CandidateRejected):
            RunState("run_1","held").advance("candidate")

    def test_candidate_is_not_production(self):
        status=RunState("run_1","candidate")
        with self.assertRaises(CandidateRejected):
            status.advance("production")
        self.assertFalse(decide(status).model_activation_allowed)

    def test_recovery_does_not_retry_ambiguous_run(self):
        result=decide(RunState("run_1","training"))
        self.assertFalse(result.retry_authorized)


if __name__ == "__main__":
    unittest.main()
