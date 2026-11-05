"""outbox_delivery: actual owner delegation and fail-closed release source checks."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.families.outbox_delivery import lifecycle
S=Scope("local","owner","a"*64,"b"*64)
HEAD="c"*64

class OutboxDeliveryLifecycleTests(unittest.TestCase):
    def test_exact_ten_final_head_gates(self):
        checks=tuple(lifecycle.CheckEvidence(name,HEAD,"success",i+1)
                     for i,name in enumerate(lifecycle.REQUIRED_CHECKS))
        result=lifecycle.release(commit_sha256=HEAD,checks=checks,
            model_rights_observed=True,native_inference_observed=True,
            laptop_device_observed=True,clean_install_observed=True,
            independent_review_observed=True)
        self.assertTrue(result["all_declared_checks_success"])
        self.assertFalse(result["release_certified"])

    def test_stale_head_refused(self):
        checks=tuple(lifecycle.CheckEvidence(name,"d"*64,"success",i+1)
                     for i,name in enumerate(lifecycle.REQUIRED_CHECKS))
        with self.assertRaises(CognitionError):
            lifecycle.release(commit_sha256=HEAD,checks=checks,
                model_rights_observed=True,native_inference_observed=True,
                laptop_device_observed=True,clean_install_observed=True,
                independent_review_observed=True)

    def test_acknowledgment_is_inert(self):
        result=lifecycle.ack_intent(S,event_key="evt",event_sha256="e"*64,request_id="r")
        self.assertFalse(result["acknowledged"])

    def test_replay_requires_canonical_worker(self):
        with self.assertRaises(CognitionError):
            lifecycle.replay(None,S,session_id="s",request_id="r",prompt="hello")

    def test_lifecycle_contract_does_not_claim_release(self):
        result=lifecycle.contract()
        self.assertFalse(result["native_execution_requested"])
        self.assertFalse(result["release_certified"])

if __name__=="__main__":
    unittest.main()
