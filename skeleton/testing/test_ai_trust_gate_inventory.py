"""Deterministic repository corpus inventory and qualification preflight."""
import re
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.inventory import inventory,qualification_snapshot

class InventoryChecks(unittest.TestCase):
    def test_complete_fixed_inventory(self):
        report=inventory()
        self.assertEqual(report["gates"],20)
        self.assertEqual(report["source_files"],280)
        self.assertEqual(report["fixture_cases"],240)
        self.assertRegex(report["source_digest"],r"^[a-f0-9]{64}$")
        self.assertEqual(report["status"],"source-tree-structurally-complete")
    def test_source_digest_is_deterministic(self):
        self.assertEqual(inventory()["source_digest"],inventory()["source_digest"])
    def test_only_explicit_fixture_run_is_accepted(self):
        result=qualification_snapshot(execute_fixtures=True)
        self.assertEqual(result["fixtures_executed"],240)
        self.assertEqual(result["expected_denials_observed"],200)
        self.assertEqual(result["status"],"source-fixtures-verified")
    def test_reject_untyped_execution_flag(self):
        with self.assertRaises(GateViolation):
            qualification_snapshot(execute_fixtures="True")

if __name__=="__main__":
    unittest.main()
