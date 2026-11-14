"""Executable original learning_rate policy vectors, not model-quality fixtures."""
from __future__ import annotations
from dataclasses import replace
import unittest

from skeleton.ai.runtime.operational_ai.native_genesis.vector_catalog import (
    iter_vectors, PolicyVector, SCHEMA,
)
from skeleton.ai.runtime.operational_ai.native_genesis.vector_runner import (
    evaluate,
)
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestLearningRateGenesisVectors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = tuple(item for item in iter_vectors()
                            if item.category == "learning_rate")

    def test_complete_independent_twelve_decisions(self):
        self.assertEqual(len(self.vectors), 12)
        self.assertEqual({v.expected for v in self.vectors}, {"allowed", "denied"})
        self.assertEqual(sum(v.expected == "allowed" for v in self.vectors), 6)
        self.assertEqual(sum(v.expected == "denied" for v in self.vectors), 6)

    def test_each_fresh_case_executes_real_policy(self):
        for vector in self.vectors:
            with self.subTest(vector=vector.vector_id):
                outcome = evaluate(vector)
                self.assertTrue(outcome.passed, outcome.record())
                self.assertEqual(outcome.observed, vector.expected)

    def test_disallowed_policy_cannot_be_normalized_into_approval(self):
        for vector in self.vectors:
            if vector.expected != "denied":
                continue
            with self.subTest(vector=vector.vector_id):
                outcome = evaluate(vector)
                self.assertEqual(outcome.observed, "denied")
                self.assertTrue(outcome.passed)

    def test_allowed_policy_remains_candidate_only(self):
        for vector in self.vectors:
            if vector.expected != "allowed":
                continue
            policy = GenesisPolicy.from_record({
                "operator_approved": True, **vector.overrides,
            })
            self.assertTrue(policy.candidate_only)
            self.assertFalse(hasattr(policy, "release_authorized"))

    def test_every_case_has_unique_content_address(self):
        self.assertEqual(len({case.vector_id for case in self.vectors}), 12)
        self.assertEqual(len({case.digest for case in self.vectors}), 12)
        self.assertTrue(all(len(case.digest) == 64 for case in self.vectors))

    def test_expected_outcome_tampering_fails_runner(self):
        original = next(v for v in self.vectors if v.expected == "denied")
        changed = replace(original, expected="allowed")
        self.assertFalse(evaluate(changed).passed)

    def test_unrecognized_schema_is_rejected(self):
        record = self.vectors[0].record()
        record["schema"] = "foreign.schema"
        with self.assertRaises(GenesisRejected):
            PolicyVector.from_record(record)

    def test_unknown_metadata_is_rejected(self):
        record = self.vectors[0].record()
        record["producer_override"] = "force-green"
        with self.assertRaises(GenesisRejected):
            PolicyVector.from_record(record)

    def test_vector_is_original_source_and_no_model_execution(self):
        for vector in self.vectors:
            self.assertTrue(vector.vector_id.startswith("learning_rate_"))
            self.assertEqual(vector.record()["schema"], SCHEMA)
            self.assertFalse(hasattr(vector, "trained_model"))
            self.assertNotIn("weights", vector.record())


if __name__ == "__main__":
    unittest.main()
