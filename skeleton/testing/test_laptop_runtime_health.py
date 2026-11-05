"""Offline laptop runtime qualification: health; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.health_levels import classify
from skeleton.ai.runtime.operational_ai.laptop_runtime.readiness import release_holds
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestHealth(unittest.TestCase):
    def test_no_unknown_health_claim_becomes_success(self):
        values={"source_inventory":True,"installed_model":False,"native_loaded":False,
                "native_canary":False,"laptop_e2e":False,"release_signoff":False}
        self.assertEqual(classify(values)["status"],"source-inventory")
        self.assertFalse(classify(values)["release_certified"])
        with self.assertRaises(ContractViolation):
            classify({**values,"native_loaded":True})
    def test_all_release_holds_are_initially_explicit(self):
        holds=release_holds()
        self.assertFalse(holds["release_certified"])
        self.assertFalse(holds["native_model_e2e"])
        self.assertFalse(holds["exact_head_github_checks"])

if __name__=="__main__":
    unittest.main()
