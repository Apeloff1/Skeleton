"""672 independent scenario files invoke live SQLite and security boundaries."""
from __future__ import annotations
import unittest
from collections import Counter

from skeleton.ai.runtime.operational_ai.durable_jobs.scenario_runner import (
    DOMAINS, TOTAL_CASES, CASES_PER_DOMAIN,iter_cases,run_matrix,
)


class TestDurableJobMatrix(unittest.TestCase):
    def test_inventory_complete_and_unique(self):
        self.assertEqual(len(DOMAINS),21)
        self.assertEqual(TOTAL_CASES,672)
        cases=list(iter_cases())
        self.assertEqual(len(cases),672)
        self.assertEqual(len({c["id"] for c in cases}),672)
        self.assertEqual(set(Counter(c["domain"] for c in cases).values()),{32})

    def test_all_cases_execute_live_gates(self):
        report=run_matrix()
        self.assertEqual(report["passed"],672,report["failures"])
        self.assertEqual(report["failed"],0)
        self.assertFalse(report["real_model_tested"])
        self.assertFalse(report["release_certified"])

    def test_all_domains_include_denials(self):
        cases=list(iter_cases())
        for domain in DOMAINS:
            local=[c for c in cases if c["domain"]==domain]
            self.assertTrue(any(c["expected_allow"] for c in local),domain)
            self.assertTrue(any(not c["expected_allow"] for c in local),domain)


if __name__=="__main__":
    unittest.main()
