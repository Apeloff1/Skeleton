"""Restore phases remain incomplete until operator/model-bound evidence is supplied."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.restore import RestoreCustody
from skeleton.ai.runtime.operational_ai.trust_gates.control.recovery_plan import RecoveryPlan
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation

class RestoreCases(unittest.TestCase):
    def test_restore_requires_all_source_evidence_phases(self):
        plan=RestoreCustody(request_id="restart",source_epoch=1)
        with self.assertRaises(Rejected):
            plan.authorize_replay(approved=True,observed_model_sha="a"*64,
                                  expected_model_sha="a"*64)
        with self.assertRaises(GateViolation):
            plan.advance("restored","b"*64)
        for i,phase in enumerate(RecoveryPlan.PHASES[1:]):
            plan.advance(phase,hex(i+10)[2:].rjust(64,"0"))
        result=plan.authorize_replay(approved=True,observed_model_sha="a"*64,
                                      expected_model_sha="a"*64)
        self.assertTrue(result["replay_permitted"])
        self.assertFalse(result["native_inference_already_restarted"])
    def test_wrong_model_epoch_cannot_restart(self):
        plan=RestoreCustody(request_id="restart2",source_epoch=1)
        for i,phase in enumerate(RecoveryPlan.PHASES[1:]):
            plan.advance(phase,hex(i+20)[2:].rjust(64,"0"))
        with self.assertRaises(Rejected):
            plan.authorize_replay(approved=True,observed_model_sha="c"*64,
                                  expected_model_sha="a"*64)

if __name__=="__main__":unittest.main()
