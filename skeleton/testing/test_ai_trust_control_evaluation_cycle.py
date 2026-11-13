"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.evaluation_cycle import EvaluationCycle
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestEvaluationCycle(unittest.TestCase):
    def test_real_counts_reconcile_to_receipt(self):
        cycle=EvaluationCycle("suite","a"*64,"b"*64,maximum_samples=3)
        cycle.observe("pass");cycle.observe("fail");cycle.observe("empty-error")
        self.assertEqual(cycle.snapshot()["samples"],3)
        with self.assertRaises(GateViolation):cycle.observe("pass")
        self.assertEqual(cycle.close(approved=True)["status"],"accepted")
        with self.assertRaises(GateViolation):cycle.close(approved=True)
    def test_no_empty_or_unapproved_evaluation(self):
        cycle=EvaluationCycle("suite","a"*64,"b"*64)
        with self.assertRaises(GateViolation):cycle.close(approved=True)
        cycle.observe("pass")
        with self.assertRaises(GateViolation):cycle.close(approved=False)

if __name__=="__main__":
    unittest.main()
