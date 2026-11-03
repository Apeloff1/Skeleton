"""Focused operational AI reliability test: circuit. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.circuit import Circuit
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class CircuitTests(unittest.TestCase):
    def test_failures_open_fence_and_reset_requires_cas(self):
        breaker=Circuit(failure_ceiling=2)
        breaker.failure()
        stopped=breaker.failure()
        self.assertEqual(stopped["status"],"open")
        with self.assertRaises(Rejected):breaker.admit()
        with self.assertRaises(Rejected):breaker.reset(operator_approval=True,expected_revision=0)
        with self.assertRaises(Rejected):breaker.reset(operator_approval=False,expected_revision=2)
        self.assertEqual(breaker.reset(operator_approval=True,expected_revision=2)["status"],"closed")
    def test_success_cannot_clear_open_circuit_implicitly(self):
        breaker=Circuit(failure_ceiling=1)
        breaker.failure()
        with self.assertRaises(Rejected):breaker.success()

if __name__=="__main__":
    unittest.main()
