"""Independent 32-vector SQLite-backed capacity native work acceptance."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import evaluate
from skeleton.ai.runtime.operational_ai.durable_jobs.scenario_runner import iter_cases


class TestCapacityDurableJobs(unittest.TestCase):
    """Validate global and per-tenant work caps independently from the entire suite."""

    def setUp(self):
        self.cases=[case for case in iter_cases() if case["domain"]=="capacity"]

    def test_all_32_executable_security_boundaries(self):
        self.assertEqual(len(self.cases),32)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                actual=evaluate(case["domain"],case["input"])
                self.assertIs(actual["allowed"],case["expected_allow"],actual)
                if case["expected_allow"]:
                    self.assertEqual(actual.get("state"),case["expected_state"])
                else:
                    self.assertTrue(actual.get("code"))

    def test_no_duplicate_vector_names(self):
        self.assertEqual(len({case["id"] for case in self.cases}),32)

    def test_permitted_and_adversarial_denials_both_observed(self):
        self.assertTrue(any(case["expected_allow"] for case in self.cases))
        self.assertTrue(any(not case["expected_allow"] for case in self.cases))

    def test_reviewable_versioned_fixtures(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["schema"],"skeleton.ai.jobs.case.v1")
                self.assertEqual(case["domain"],"capacity")
                self.assertTrue(case["threat"])
                self.assertFalse(case["no_synthetic_production_model"] is False)
                self.assertIs(case["device_qualified"],False)
                self.assertIs(case["release_certified"],False)


if __name__=="__main__":
    unittest.main()
