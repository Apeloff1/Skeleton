"""Trainer, evaluator, release and rollback roles stay distinct."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.candidate_authority import AuthorityAssignment
from skeleton.ai.runtime.operational_ai.native_candidate.review_holds import review, GateEvidence, GATES
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected


class TestCandidateRoleIsolation(unittest.TestCase):
    def test_independent_roles(self):
        roles=AuthorityAssignment("trainer","evaluator","release","rollback")
        self.assertTrue(roles.record()["role_isolation"])
        self.assertFalse(roles.record()["production_authorized"])

    def test_same_actor_cannot_verify_own_training(self):
        with self.assertRaises(CandidateRejected):
            AuthorityAssignment("trainer","trainer","release","rollback")

    def test_no_release_without_all_independent_gates(self):
        result=review(())
        self.assertFalse(result["fully_proven"])
        self.assertFalse(result["release_certified"])
        self.assertEqual(len(result["missing"]),len(GATES))

    def test_no_auto_release_even_complete_evidence_inventory(self):
        records=tuple(GateEvidence(name,True,"a"*64,"b"*64) for name in GATES)
        status=review(records)
        self.assertTrue(status["fully_proven"])
        self.assertFalse(status["merge_authorized"])
        self.assertFalse(status["release_certified"])

    def test_missing_gate_proof_refused(self):
        with self.assertRaises(CandidateRejected):
            GateEvidence("device",True)


if __name__ == "__main__":
    unittest.main()
