"""Execute all 288 real constructor decisions and source-bound outcomes."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.vector_catalog import (
    CATEGORIES, TOTAL_VECTORS, iter_vectors, inventory, PolicyVector,
)
from skeleton.ai.runtime.operational_ai.native_genesis.vector_runner import (
    evaluate, run_all,
)
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestGenesisPolicyVectorSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases=tuple(iter_vectors())

    def test_exact_counts(self):
        self.assertEqual(len(CATEGORIES),24)
        self.assertEqual(len(self.cases),TOTAL_VECTORS)
        self.assertEqual(TOTAL_VECTORS,288)

    def test_every_domain_has_twelve(self):
        for cat in CATEGORIES:
            self.assertEqual(sum(x.category==cat for x in self.cases),12)

    def test_complete_executable_results(self):
        result=run_all()
        self.assertEqual(result["cases"],288)
        self.assertEqual(result["passed"],288,result["failed_ids"])
        self.assertEqual(result["failed"],0)
        self.assertFalse(result["native_training_executed"])
        self.assertFalse(result["release_certified"])

    def test_all_original_records_are_unique(self):
        inv=inventory()
        self.assertEqual(inv["count"],288)
        self.assertEqual(len(inv["entries"]),288)
        self.assertEqual(len({x.digest for x in self.cases}),288)

    def test_policy_expectation_falsification_is_detected(self):
        target=next(v for v in self.cases if v.expected=="denied")
        altered=replace(target,expected="allowed")
        self.assertFalse(evaluate(altered).passed)

    def test_duplicate_metadata_is_rejected(self):
        row=self.cases[0].record()
        row["unexpected"]="force-release"
        with self.assertRaises(GenesisRejected):
            PolicyVector.from_record(row)

    def test_no_vectors_execute_native_weights(self):
        for item in self.cases:
            self.assertNotIn("checkpoint",item.overrides)
            self.assertNotIn("weights",item.record())
            self.assertNotIn("training_result",item.record())


if __name__=="__main__":
    unittest.main()
