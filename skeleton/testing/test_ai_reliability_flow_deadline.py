"""Focused operational AI reliability test: deadline. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.deadline import Deadline,RetryFence
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class DeadlineTests(unittest.TestCase):
    def test_child_deadline_never_extends_parent(self):
        now=[100]
        root=Deadline(duration_ns=1000,clock=lambda:now[0])
        child=root.child(5000)
        self.assertEqual(child.remaining_ns(),1000)
        now[0]=1100
        with self.assertRaises(Rejected):root.check()
    def test_retries_only_when_side_effect_absent(self):
        budget=RetryFence(maximum=2,initial_ms=100,ceiling_ms=150)
        self.assertEqual(budget.next_delay_ms(failure_retryable=True,side_effect_known_absent=True),100)
        self.assertEqual(budget.next_delay_ms(failure_retryable=True,side_effect_known_absent=True),150)
        with self.assertRaises(Rejected):budget.next_delay_ms(failure_retryable=True,side_effect_known_absent=True)
        with self.assertRaises(Rejected):RetryFence().next_delay_ms(failure_retryable=True,side_effect_known_absent=False)

if __name__=="__main__":
    unittest.main()
