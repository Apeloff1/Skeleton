"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.testing.reliability_fabric_test_support import scenario,FakeWorker
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.preflight import inspect,REQUIRED_INFERENCE
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.worker=FakeWorker()
        self.records={name:scenario(name,subject="owner") for name in REQUIRED_INFERENCE}
    def test_full_nine_boundary_preflight(self):
        receipt=inspect(self.worker,self.records)
        self.assertEqual(len(receipt.receipt.domains),9)
        self.assertFalse(receipt.native_generation_performed)
        self.assertEqual(self.worker.generation_calls,0)
    def test_missing_boundary_blocks_model(self):
        del self.records["lease_epoch"]
        with self.assertRaises(Rejected):inspect(self.worker,self.records)
    def test_wrong_model_identity_blocks_model(self):
        self.records["native_identity"]["identity"]["model_sha256"]="f"*64
        with self.assertRaises(Rejected):inspect(self.worker,self.records)
if __name__=="__main__":unittest.main()
