"""Original source completeness, rights and held-out split, no copied benchmarks."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.source import verify_source
from skeleton.ai.runtime.operational_ai.native_genesis.rights_fence import confirm
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy


class TestGenesisSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=verify_source()

    def test_original_exact_source(self):
        self.assertEqual(len(self.source.training_lines),432)
        self.assertTrue(self.source.original_answers_valid)
        self.assertTrue(self.source.benchmark_overlap_clear)

    def test_held_out_samples_protected(self):
        self.assertEqual(len(self.source.partitions.validation),72)
        self.assertEqual(len(self.source.partitions.holdout),72)
        self.assertEqual(len(self.source.partitions.train),432)
        ids={i.item_id for i in self.source.partitions.train}
        self.assertFalse(ids & {i.item_id for i in self.source.partitions.validation})
        self.assertFalse(ids & {i.item_id for i in self.source.partitions.holdout})

    def test_three_cryptographic_source_bindings(self):
        report=self.source.report()
        for key in ("source_sha256","partitions_sha256","rights_sha256","curriculum_sha256"):
            with self.subTest(field=key):
                self.assertEqual(len(report[key]),64)

    def test_rights_are_scoped_to_training_only(self):
        report=confirm(self.source,GenesisPolicy(operator_approved=True))
        self.assertEqual(report["permitted_purpose"],"offline_native_candidate_training")
        self.assertFalse(report["serving_rights_granted"])

    def test_source_does_not_claim_trained_weights(self):
        report=self.source.report()
        self.assertFalse(report["has_trained_weights"])
        self.assertFalse(report["release_qualified"])
        self.assertFalse(report["near_duplicate_review_complete"])


if __name__=="__main__":
    unittest.main()
