"""Focused operational AI reliability test: preflight. No synthetic native E2E claim."""
import unittest
from skeleton.testing.reliability_fabric_test_support import scenario,FakeWorker
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.preflight import inspect,REQUIRED_INFERENCE
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.records={name:scenario(name,subject="owner") for name in REQUIRED_INFERENCE}
    def test_complete_pinned_spine_preflight(self):
        proof=inspect(self.worker,self.records)
        self.assertFalse(proof.native_generation_performed)
        self.assertEqual(len(proof.receipt.domains),9)
        self.assertEqual(self.worker.generation_calls,0)
    def test_missing_gate_never_generates(self):
        del self.records["model_capacity"]
        with self.assertRaises(Rejected):inspect(self.worker,self.records)
        self.assertEqual(self.worker.generation_calls,0)
    def test_cross_tenant_source_fails_before_effect(self):
        self.records["admission_queue"]["identity"]["subject"]="other"
        with self.assertRaises(Rejected):inspect(self.worker,self.records)

if __name__=="__main__":
    unittest.main()
