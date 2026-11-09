"""Offline laptop runtime qualification: permissions; test-double only, not real native E2E."""
import unittest
from skeleton.ai.runtime.operational_ai.laptop_runtime.safety_mode import SafetyMode
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import ContractViolation
class TestSafetyPolicy(unittest.TestCase):
    def test_strict_offline_operator_policy_is_default(self):
        record=SafetyMode().to_record()
        self.assertFalse(record["allow_network"])
        self.assertFalse(record["allow_remote_provider"])
        self.assertFalse(record["model_tool_authority"])
        self.assertTrue(record["require_isolation"])
    def test_tools_network_and_implicit_memory_are_not_runtime_flags(self):
        for option,bad in (("allow_network",True),("model_tool_authority",True),
                           ("allow_implicit_memory",True),("allow_remote_provider",True),
                           ("require_isolation",False),("require_source_receipt",False)):
            with self.subTest(option=option):
                with self.assertRaises(ContractViolation):SafetyMode(**{option:bad})

if __name__=="__main__":
    unittest.main()
