"""Focused operational AI reliability test: rollout_plan. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.rollout_plan import prepare
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.applications.release_evidence import REQUIRED
class RolloutTests(unittest.TestCase):
    def test_unobserved_status_source_never_authorizes_rollout(self):
        data={k:"success" for k in REQUIRED}
        with self.assertRaises(Rejected):
            prepare(head_sha256="a"*64,model_sha256="b"*64,token_sha256="c"*64,
                    check_statuses=data,reviewer_approved=True,native_e2e=True,
                    rights_approved=True,installation_qualified=True,
                    source_of_statuses="fixture")
    def test_skipped_ci_check_refuses_ready_metadata(self):
        data={k:"success" for k in REQUIRED}
        data["Malware Gate"]="skipped"
        with self.assertRaises(GateViolation):
            prepare(head_sha256="a"*64,model_sha256="b"*64,token_sha256="c"*64,
                    check_statuses=data,reviewer_approved=True,native_e2e=True,
                    rights_approved=True,installation_qualified=True,
                    source_of_statuses="actual-final-head-github-api")

if __name__=="__main__":
    unittest.main()
