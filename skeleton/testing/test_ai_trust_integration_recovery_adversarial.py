"""Restore evidence can never skip, repeat or reorder a custody phase."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.control.recovery_plan import RecoveryPlan

class RecoveryAdversarial(unittest.TestCase):
    def test_every_skip_is_refused(self):
        for stage in RecoveryPlan.PHASES[2:]:
            with self.subTest(stage=stage):
                plan=RecoveryPlan(request_id="r",source_epoch=1)
                with self.assertRaises(GateViolation):
                    plan.advance(stage,evidence_sha="a"*64)
    def test_zero_and_missing_hash_are_refused(self):
        for evidence in (None,"","0"*64,"not-a-sha"):
            with self.subTest(evidence=evidence):
                plan=RecoveryPlan(request_id="r",source_epoch=1)
                with self.assertRaises(GateViolation):
                    plan.advance("inventory-verified",evidence_sha=evidence)
    def test_repeated_stage_is_refused(self):
        plan=RecoveryPlan(request_id="r",source_epoch=1)
        plan.advance("inventory-verified",evidence_sha="a"*64)
        with self.assertRaises(GateViolation):
            plan.advance("inventory-verified",evidence_sha="b"*64)
    def test_replay_refused_before_terminal_stage(self):
        plan=RecoveryPlan(request_id="r",source_epoch=1)
        for idx,stage in enumerate(RecoveryPlan.PHASES[1:-1]):
            plan.advance(stage,evidence_sha=hex(idx+20)[2:].rjust(64,"0"))
            self.assertFalse(plan.can_replay())
        plan.advance("restored",evidence_sha="f"*64)
        self.assertTrue(plan.can_replay())
        self.assertEqual(len(plan.evidence()),len(RecoveryPlan.PHASES)-1)

if __name__=="__main__": unittest.main()
