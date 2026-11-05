"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.deadline import Deadline,RetryFence
from skeleton.ai.runtime.operational_ai.reliability_fabric.contracts import Rejected
class TimeBoundaries(unittest.TestCase):
    def test_deadline_child_never_extends_root(self):
        clock=[100]
        parent=Deadline(duration_ns=1000,clock=lambda:clock[0])
        child=parent.child(5000)
        self.assertEqual(child.remaining_ns(),1000)
        clock[0]=1100
        with self.assertRaises(Rejected):parent.check()
    def test_retry_requires_proved_absence_of_effects(self):
        budget=RetryFence(maximum=2,initial_ms=100,ceiling_ms=150)
        self.assertEqual(budget.next_delay_ms(failure_retryable=True,side_effect_known_absent=True),100)
        self.assertEqual(budget.next_delay_ms(failure_retryable=True,side_effect_known_absent=True),150)
        with self.assertRaises(Rejected):
            budget.next_delay_ms(failure_retryable=True,side_effect_known_absent=True)
        with self.assertRaises(Rejected):
            RetryFence().next_delay_ms(failure_retryable=True,side_effect_known_absent=False)
if __name__=="__main__":unittest.main()
