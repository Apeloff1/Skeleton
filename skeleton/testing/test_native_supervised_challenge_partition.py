"""Challenge partition plan forbids training fixture exposure and skipped groups."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_partition import plan
from skeleton.ai.runtime.operational_ai.native_supervised.bounded_slices import (
    create_slices,verify_slices,
)
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_overlap import scan


class TestIndependentChallengePartition(unittest.TestCase):
    def test_all_challenges_reserved_for_evaluation(self):
        result=plan()
        self.assertEqual(len(result.cases),768)
        self.assertEqual(result.critical_count,192)
        self.assertEqual(result.normal_count,576)
        self.assertEqual(result.report()["train_cases"],0)
        self.assertFalse(result.report()["candidate_training_labels_exposed"])

    def test_exact_32_domain_slices(self):
        work=create_slices()
        self.assertEqual(len(work),32)
        self.assertEqual([x.start for x in work],list(range(0,768,24)))
        self.assertEqual({x.count for x in work},{24})

    def test_each_slice_binds_source_sha(self):
        for item in create_slices():
            self.assertEqual(len(item.source_sha256),64)
            self.assertEqual(item.domain,plan().cases[item.start].domain)

    def test_source_slices_are_deterministic(self):
        self.assertEqual(create_slices(),create_slices())
        self.assertFalse(verify_slices(create_slices())["actually_executed"])

    def test_exact_overlap_scan(self):
        result=scan()
        self.assertTrue(result["exact_clear"])
        self.assertEqual(result["exact_training_overlap"],0)
        self.assertEqual(result["exact_other_benchmark_overlap"],0)
        self.assertFalse(result["independent_near_duplicate_review_complete"])


if __name__=="__main__":
    unittest.main()
