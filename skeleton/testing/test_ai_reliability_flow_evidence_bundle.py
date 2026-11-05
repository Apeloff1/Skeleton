"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.testing.reliability_fabric_test_support import scenario
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.evidence_bundle import EvidenceBundle
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class BundleTests(unittest.TestCase):
    def test_two_boundaries_share_actor_model_and_time(self):
        item=EvidenceBundle()
        item.add("native_identity",scenario("native_identity"))
        item.add("tokenizer_custody",scenario("tokenizer_custody"))
        sealed=item.seal(required=("native_identity","tokenizer_custody"))
        self.assertEqual(len(sealed.domains),2)
        self.assertFalse(sealed.release_certified)
    def test_cross_subject_bundle_and_omitted_evidence_refused(self):
        item=EvidenceBundle()
        item.add("native_identity",scenario("native_identity"))
        with self.assertRaises(Rejected):
            item.add("tokenizer_custody",scenario("tokenizer_custody",subject="other"))
        with self.assertRaises(Rejected):
            item.seal(required=("native_identity","tokenizer_custody"))
    def test_sealed_bundle_is_not_mutable(self):
        item=EvidenceBundle()
        item.add("native_identity",scenario("native_identity"))
        item.seal(required=("native_identity",))
        with self.assertRaises(Rejected):
            item.add("tool_grant",scenario("tool_grant"))
if __name__=="__main__":unittest.main()
