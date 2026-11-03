"""Real SFT source excludes validation/holdout and independently verifies rights."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_supervised.source import prepare_source
from skeleton.ai.runtime.operational_ai.native_supervised.source_manifest import generate
from skeleton.ai.runtime.operational_ai.native_supervised.challenge_catalog import inventory


class TestSupervisedSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope=prepare_source()

    def test_original_source_and_license(self):
        self.assertEqual(self.scope.train_count,432)
        self.assertEqual(self.scope.validation_count,72)
        self.assertEqual(self.scope.holdout_count,72)
        self.assertEqual(len(self.scope.corpus_sha256),64)
        self.assertEqual(len(self.scope.rights_sha256),64)

    def test_training_validation_holdout_disjoint(self):
        splits=(self.scope.groups.train,self.scope.groups.validation,
                self.scope.groups.holdout)
        ids=[{x.item_id for x in part} for part in splits]
        self.assertFalse(ids[0]&ids[1])
        self.assertFalse(ids[0]&ids[2])
        self.assertFalse(ids[1]&ids[2])

    def test_separate_768_evaluation_cases(self):
        records=inventory()
        self.assertEqual(records["count"],768)
        self.assertEqual(len(records["domains"]),32)
        self.assertFalse(records["trained_on_challenges"])

    def test_independent_source_manifest(self):
        manifest=generate()
        self.assertEqual(manifest.evaluation_cases,768)
        self.assertEqual(manifest.training_sha256,self.scope.corpus_sha256)
        self.assertEqual(manifest.partition_sha256,self.scope.partition_sha256)
        self.assertFalse(manifest.record()["release_certified"])

    def test_source_only_does_not_create_weights(self):
        self.assertFalse(self.scope.record()["weights_created"])
        self.assertFalse(self.scope.record()["release_certified"])


if __name__=="__main__":
    unittest.main()
