"""Focused operational AI reliability test: restore. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.restore import RestoreCustody
from skeleton.ai.runtime.operational_ai.trust_gates.control.recovery_plan import RecoveryPlan
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class RestoreTests(unittest.TestCase):
    def test_all_ordered_phases_then_explicit_restart_authority(self):
        plan=RestoreCustody(request_id="restore",source_epoch=1)
        with self.assertRaises(Rejected):
            plan.authorize_replay(approved=True,observed_model_sha="a"*64,
                                expected_model_sha="a"*64)
        for i,phase in enumerate(RecoveryPlan.PHASES[1:]):
            plan.advance(phase,hex(i+10)[2:].rjust(64,"0"))
        result=plan.authorize_replay(approved=True,
                    observed_model_sha="a"*64,expected_model_sha="a"*64)
        self.assertTrue(result["replay_permitted"])
        self.assertFalse(result["native_inference_already_restarted"])

if __name__=="__main__":
    unittest.main()
