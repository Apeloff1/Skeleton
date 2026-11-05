"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.deadline import Deadline,RetryBudget
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestDeadline(unittest.TestCase):
    def test_child_does_not_extend_parent(self):
        now=[100]
        parent=Deadline(1000,clock=lambda:now[0])
        child=parent.child(5000)
        self.assertEqual(child.end_ns,1000)
        now[0]=1000
        with self.assertRaises(GateViolation):parent.require_live()
    def test_bounded_fail_closed_retries(self):
        policy=RetryBudget(attempts=2,base_ms=100,ceiling_ms=150)
        self.assertEqual(policy.next_delay_ms(retryable=True),100)
        self.assertEqual(policy.next_delay_ms(retryable=True),150)
        with self.assertRaises(GateViolation):policy.next_delay_ms(retryable=True)
        with self.assertRaises(GateViolation):RetryBudget().next_delay_ms(retryable=False)

if __name__=="__main__":
    unittest.main()
