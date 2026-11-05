"""Executable original privacy admission contract vectors."""
from __future__ import annotations
import unittest

from skeleton.ai.runtime.operational_ai.native_candidate.vector_catalog import read_cases
from skeleton.ai.runtime.operational_ai.native_candidate.vector_evaluator import evaluate
from skeleton.ai.runtime.operational_ai.native_candidate.strict import encode, decode


class TestPrivacyCandidateBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = tuple(row for row in read_cases() if row["domain"] == "privacy")

    def test_exact_24_independent_source_vectors(self):
        self.assertEqual(len(self.rows), 24)
        self.assertEqual(len({row["id"] for row in self.rows}), 24)
        self.assertTrue(all(row["id"].startswith("privacy_") for row in self.rows))

    def test_live_admission_matches_fixed_expectations(self):
        for case in self.rows:
            with self.subTest(case=case["id"]):
                outcome = evaluate("privacy", case["input"])
                self.assertIs(outcome["allowed"], case["expected_allow"])
                self.assertIsInstance(outcome["code"], str)

    def test_both_approved_and_rejected_inputs_exist(self):
        self.assertTrue(any(row["expected_allow"] for row in self.rows))
        self.assertTrue(any(not row["expected_allow"] for row in self.rows))

    def test_original_json_cannot_claim_model_quality(self):
        for case in self.rows:
            with self.subTest(case=case["id"]):
                self.assertFalse(case["model_qualified"])
                self.assertFalse(case["release_certified"])
                self.assertEqual(
                    decode(encode(case))["id"],
                    case["id"],
                )

    def test_source_is_not_a_model_generated_pass(self):
        for case in self.rows:
            self.assertNotIn("model_reply", case)
            self.assertNotIn("model_output", case)
            self.assertNotIn("final_inference_receipt", case)


if __name__ == "__main__":
    unittest.main()
