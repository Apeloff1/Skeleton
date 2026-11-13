"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.rollout_plan import prepare
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.applications.release_evidence import REQUIRED
class RolloutCases(unittest.TestCase):
    def test_fabricated_ci_source_does_not_qualify(self):
        checks={name:"success" for name in REQUIRED}
        with self.assertRaises(Rejected):
            prepare(head_sha256="a"*64,model_sha256="b"*64,token_sha256="c"*64,
                    check_statuses=checks,reviewer_approved=True,native_e2e=True,
                    rights_approved=True,installation_qualified=True,
                    source_of_statuses="fixture")
    def test_skipped_security_gate_cannot_be_pass(self):
        checks={name:"success" for name in REQUIRED};checks["Malware Gate"]="skipped"
        with self.assertRaises(GateViolation):
            prepare(head_sha256="a"*64,model_sha256="b"*64,token_sha256="c"*64,
                    check_statuses=checks,reviewer_approved=True,native_e2e=True,
                    rights_approved=True,installation_qualified=True,
                    source_of_statuses="actual-final-head-github-api")
if __name__=="__main__":unittest.main()
