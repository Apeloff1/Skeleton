"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.circuit import Circuit
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class NativeCircuitTests(unittest.TestCase):
    def test_failure_ceiling_requires_approved_compare_and_set_reset(self):
        c=Circuit(failure_ceiling=2)
        c.failure();self.assertEqual(c.failure()["status"],"open")
        with self.assertRaises(Rejected):c.admit()
        with self.assertRaises(Rejected):
            c.reset(operator_approval=True,expected_revision=0)
        with self.assertRaises(Rejected):
            c.reset(operator_approval=False,expected_revision=2)
        self.assertEqual(c.reset(operator_approval=True,expected_revision=2)["status"],"closed")
    def test_success_cannot_erase_open_failure(self):
        c=Circuit(failure_ceiling=1)
        c.failure()
        with self.assertRaises(Rejected):c.success()
if __name__=="__main__":unittest.main()
