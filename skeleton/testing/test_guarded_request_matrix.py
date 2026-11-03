"""384 independent security/capacity cases, without model inference or quality claims."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import (
    DOMAINS, TOTAL_SCENARIOS, iter_scenarios, verify_all,
)


class TestGuardedRequestMatrix(unittest.TestCase):
    def test_exact_control_inventory(self):
        self.assertEqual(len(DOMAINS), 16)
        self.assertEqual(TOTAL_SCENARIOS, 384)
        all_cases = list(iter_scenarios())
        self.assertEqual(len(all_cases), TOTAL_SCENARIOS)
        self.assertEqual(len({case["id"] for case in all_cases}), TOTAL_SCENARIOS)

    def test_fresh_executable_control_matrix(self):
        report = verify_all()
        self.assertEqual(report["total"], 384)
        self.assertEqual(report["failed"], 0, report["failure_ids"])
        self.assertEqual(report["passed"], 384)
        self.assertFalse(report["real_model_tested"])
        self.assertFalse(report["release_certified"])

    def test_all_domains_include_denials(self):
        cases = list(iter_scenarios())
        for domain in DOMAINS:
            group = [c for c in cases if c["control"] == domain]
            self.assertEqual(len(group), 24)
            self.assertTrue(any(c["expected_allow"] for c in group))
            self.assertTrue(any(not c["expected_allow"] for c in group))


if __name__ == "__main__":
    unittest.main()
