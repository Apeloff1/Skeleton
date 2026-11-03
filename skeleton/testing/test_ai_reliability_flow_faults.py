"""Focused operational AI reliability test: faults. No synthetic native E2E claim."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.faults import classify
class FaultTests(unittest.TestCase):
    def test_unknown_fails_closed(self):
        result=classify("invented")
        self.assertFalse(result.retry_allowed)
        self.assertTrue(result.operator_required)
        self.assertTrue(result.native_effect_unknown)
    def test_capacity_retry_is_distinct_from_uncertain_native(self):
        self.assertTrue(classify("queue-saturated").retry_allowed)
        self.assertFalse(classify("native-timeout").retry_allowed)

if __name__=="__main__":
    unittest.main()
