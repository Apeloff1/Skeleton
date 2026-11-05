"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.recovery_plan import RecoveryPlan
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestRecoveryPlan(unittest.TestCase):
    def test_replay_only_after_six_evidence_stages(self):
        plan=RecoveryPlan(request_id="restore",source_epoch=1)
        self.assertFalse(plan.can_replay())
        with self.assertRaises(GateViolation):plan.advance("restored",evidence_sha="a"*64)
        for i,name in enumerate(RecoveryPlan.PHASES[1:]):
            plan.advance(name,evidence_sha=hex(i+10)[2:].rjust(64,"0"))
        self.assertTrue(plan.can_replay())
    def test_duplicate_evidence_denied(self):
        plan=RecoveryPlan(request_id="r",source_epoch=1)
        plan.advance("inventory-verified",evidence_sha="a"*64)
        with self.assertRaises(GateViolation):plan.advance("keys-verified",evidence_sha="a"*64)

if __name__=="__main__":
    unittest.main()
