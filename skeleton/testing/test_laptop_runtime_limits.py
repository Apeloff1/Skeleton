"""Offline laptop runtime qualification: limits; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.deployment_profile import LaptopProfile
from skeleton.ai.runtime.operational_ai.laptop_runtime.limits_bridge import describe
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
from skeleton.testing.laptop_runtime_test_support import FakeWorker
class TestLimits(unittest.TestCase):
    def test_operator_budget_can_only_attenuate(self):
        base=LaptopProfile()
        lowered=base.attenuate(max_new_tokens=128,threads=2)
        self.assertEqual(lowered.max_new_tokens,128)
        with self.assertRaises(ContractViolation):
            base.attenuate(max_new_tokens=512)
    def test_real_spine_limits_observed_without_escalation(self):
        record=describe(FakeWorker().spine.limits)
        self.assertFalse(record["client_may_raise_limits"])
        self.assertEqual(record["limits"]["context_tokens"],2048)

if __name__=="__main__":
    unittest.main()
