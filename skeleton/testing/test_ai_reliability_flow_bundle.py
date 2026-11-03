"""Focused operational AI reliability test: bundle. No synthetic native E2E claim."""
import unittest
from skeleton.testing.reliability_fabric_test_support import scenario
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.evidence_bundle import EvidenceBundle
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class BundleTests(unittest.TestCase):
    def test_two_domains_seal_same_actor_epoch(self):
        book=EvidenceBundle(maximum=2)
        a=book.add("native_identity",scenario("native_identity"))
        book.add("tokenizer_custody",scenario("tokenizer_custody"))
        receipt=book.seal(required=("native_identity","tokenizer_custody"))
        self.assertEqual(len(receipt.domains),2)
        self.assertFalse(receipt.release_certified)
        with self.assertRaises(Rejected):book.add("native_identity",scenario("native_identity"))
    def test_actor_or_model_confusion_denied(self):
        book=EvidenceBundle()
        book.add("native_identity",scenario("native_identity"))
        with self.assertRaises(Rejected):
            book.add("tool_grant",scenario("tool_grant",subject="different"))
    def test_required_evidence_cannot_be_omitted(self):
        book=EvidenceBundle()
        book.add("native_identity",scenario("native_identity"))
        with self.assertRaises(Rejected):
            book.seal(required=("native_identity","tool_grant"))

if __name__=="__main__":
    unittest.main()
