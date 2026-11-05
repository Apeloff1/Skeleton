"""No uncertain native SGD run may auto-resume or claim a successful artifact."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.run_state import RunState
from skeleton.ai.runtime.operational_ai.native_supervised.recovery import decide
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestSupervisedRecovery(unittest.TestCase):
    def test_real_fsm_order(self):
        state=RunState("original_run")
        for next_stage in ("source_verified","bootstrapped",
                           "genesis_published","training",
                           "candidate_published","evaluating",
                           "review_pending","held"):
            state=state.advance(next_stage)
        self.assertEqual(state.revision,8)
        self.assertFalse(state.report()["automatic_model_activation"])

    def test_training_can_fail_to_uncertain(self):
        state=RunState("original_run","training").advance("uncertain")
        report=decide(state,checkpoint_sha256="a"*64,
                      verified_manifest=True,pinned_audit_head=True)
        self.assertEqual(report["state"],"held")
        self.assertFalse(report["retry_same_run"])
        self.assertFalse(report["resume_training_automatically"])
        self.assertFalse(report["serving_activation"])

    def test_skipping_rights_proof_denied(self):
        with self.assertRaises(SupervisedRejected):
            RunState("original_run").advance("training")

    def test_terminal_hold_cannot_promote(self):
        with self.assertRaises(SupervisedRejected):
            RunState("original_run","held").advance("candidate_published")

    def test_missing_artifact_does_not_count_as_verified(self):
        report=decide(RunState("original_run","training"))
        self.assertFalse(report["artifact_seen"])
        self.assertEqual(report["state"],"held")


if __name__=="__main__":
    unittest.main()
