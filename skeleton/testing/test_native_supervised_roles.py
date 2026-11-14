"""Independent actors and exact-head evidence still cannot self-release models."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.authority import RoleAssignments
from skeleton.ai.runtime.operational_ai.native_supervised.release_hold import (
    REQUIRED,Gate,review,
)
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestNativeSFTAuthority(unittest.TestCase):
    def test_separate_four_custody_roles(self):
        record=RoleAssignments("trainer","evaluator","rollback","release").report()
        self.assertTrue(record["independent_actors"])
        self.assertFalse(record["model_activation_granted"])

    def test_self_approval_refused(self):
        with self.assertRaises(SupervisedRejected):
            RoleAssignments("trainer","trainer","rollback","release")

    def test_no_gates_is_not_qualification(self):
        result=review((),exact_head="a"*64)
        self.assertEqual(len(result["missing"]),len(REQUIRED))
        self.assertFalse(result["release_certified"])

    def test_pending_gate_is_not_passing(self):
        result=review((Gate("backend_quality",False),),exact_head="a"*64)
        self.assertIn("backend_quality",result["failed_or_wrong_head"])
        self.assertFalse(result["automatic_merge"])

    def test_gates_must_match_exact_head(self):
        evidence=Gate("backend_quality",True,git_sha256="b"*64,
                      evidence_sha256="c"*64)
        report=review((evidence,),exact_head="a"*64)
        self.assertIn("backend_quality",report["failed_or_wrong_head"])

    def test_even_all_green_proofs_do_not_auto_promote(self):
        evidence=tuple(Gate(name,True,git_sha256="a"*64,
                            evidence_sha256="b"*64)
                       for name in REQUIRED)
        report=review(evidence,exact_head="a"*64)
        self.assertTrue(report["all_attested"])
        self.assertFalse(report["automatic_model_promotion"])
        self.assertFalse(report["release_certified"])


if __name__=="__main__":
    unittest.main()
