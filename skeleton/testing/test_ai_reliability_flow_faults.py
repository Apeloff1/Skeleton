"""Focused runtime reliability flow checks; not real GGUF inference evidence."""
import unittest
from skeleton.ai.runtime.operational_ai.reliability_fabric.flows.faults import classify
class FaultClasses(unittest.TestCase):
    def test_unknown_effects_are_not_retryable(self):
        result=classify("not-a-real-state")
        self.assertFalse(result.retry_allowed)
        self.assertTrue(result.native_effect_unknown)
        self.assertTrue(result.operator_required)
    def test_rate_saturation_vs_native_timeout(self):
        self.assertTrue(classify("queue-saturated").retry_allowed)
        self.assertFalse(classify("native-timeout").retry_allowed)
if __name__=="__main__":unittest.main()
