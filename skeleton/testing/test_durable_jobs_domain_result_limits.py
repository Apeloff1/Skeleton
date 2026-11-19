"""Independent 32-vector SQLite-backed result_limits native work acceptance."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import evaluate
from skeleton.ai.runtime.operational_ai.durable_jobs.scenario_runner import iter_cases


class TestResultLimitsDurableJobs(unittest.TestCase):
    """Validate output token and source-identity limits independently from the entire suite."""

    def setUp(self):
        self.cases=[case for case in iter_cases() if case["domain"]=="result_limits"]

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

    def test_oversized_adversarial_receipt_still_executes_fail_closed(self):
        from skeleton.ai.runtime.operational_ai.durable_jobs.canonical import MAX_BYTES, decode
        from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
        from skeleton.ai.runtime.operational_ai.durable_jobs.scenario_runner import _read_case
        from importlib import resources
        root = resources.files("skeleton.ai.runtime.operational_ai.durable_jobs") / "scenarios" / "result_limits"
        fixture = root / "result_limits-28.json"
        self.assertGreater(len(fixture.read_bytes()), MAX_BYTES)
        with self.assertRaises(JobDenied):
            decode(fixture.read_bytes())
        case = _read_case(fixture)
        self.assertIs(case["expected_allow"], False)
        outcome = evaluate(case["domain"], case["input"])
        self.assertIs(outcome["allowed"], False)
        self.assertEqual(outcome["code"], "text-output")

    def test_other_oversized_fixture_names_remain_rejected(self):
        from skeleton.ai.runtime.operational_ai.durable_jobs.scenario_runner import _read_case
        from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
        from importlib import resources
        root = resources.files("skeleton.ai.runtime.operational_ai.durable_jobs") / "scenarios" / "result_limits"
        source = root / "result_limits-28.json"
        class OtherName:
            name = "result_limits-27.json"
            def read_bytes(self):
                return source.read_bytes()
        with self.assertRaisesRegex(JobDenied, "json-oversize"):
            _read_case(OtherName())

    def test_no_duplicate_vector_names(self):
        self.assertEqual(len({case["id"] for case in self.cases}),32)

    def test_permitted_and_adversarial_denials_both_observed(self):
        self.assertTrue(any(case["expected_allow"] for case in self.cases))
        self.assertTrue(any(not case["expected_allow"] for case in self.cases))

    def test_reviewable_versioned_fixtures(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["schema"],"skeleton.ai.jobs.case.v1")
                self.assertEqual(case["domain"],"result_limits")
                self.assertTrue(case["threat"])
                self.assertFalse(case["no_synthetic_production_model"] is False)
                self.assertIs(case["device_qualified"],False)
                self.assertIs(case["release_certified"],False)


if __name__=="__main__":
    unittest.main()
