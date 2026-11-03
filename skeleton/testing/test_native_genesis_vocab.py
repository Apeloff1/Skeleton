"""Native vocabulary actually fits 432 training lines; no holdout fitting."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_genesis.policy import GenesisPolicy
from skeleton.ai.runtime.operational_ai.native_genesis.source import verify_source
from skeleton.ai.runtime.operational_ai.native_genesis.vocabulary import build_vocabulary
from skeleton.ai.runtime.operational_ai.native_genesis.vocab_coverage import inspect
from skeleton.ai.runtime.operational_ai.native_genesis.errors import GenesisRejected


class TestGenesisVocabulary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=verify_source()
        cls.policy=GenesisPolicy(operator_approved=True)
        cls.vocab=build_vocabulary(cls.source,cls.policy)

    def test_train_only_vocabulary(self):
        report=self.vocab.report()
        self.assertEqual(report["source_documents"],432)
        self.assertFalse(report["trained_on_validation"])
        self.assertFalse(report["trained_on_holdout"])
        self.assertFalse(report["trained_on_benchmark"])

    def test_stable_token_order(self):
        self.assertEqual(self.vocab.entries,tuple(sorted(self.vocab.entries)))
        self.assertEqual(len(set(self.vocab.entries)),len(self.vocab.entries))
        self.assertTrue(all(token==token.lower() for token in self.vocab.entries))

    def test_train_coverage_is_exact_for_frequency_one(self):
        proof=inspect(self.source,self.vocab,partition="train")
        self.assertEqual(proof.unknown,0)
        self.assertEqual(proof.fraction_ppm,1000000)

    def test_holdout_is_only_observed_not_fitted(self):
        held=inspect(self.source,self.vocab,partition="holdout")
        self.assertGreater(held.total,0)
        self.assertEqual(held.source_partition,"holdout")
        self.assertFalse(held.report()["model_quality_scored"])

    def test_tight_vocab_budget_blocks_before_weight_allocation(self):
        with self.assertRaises(GenesisRejected):
            build_vocabulary(self.source,replace(self.policy,max_vocab=32))

    def test_invalid_partition_name_refused(self):
        with self.assertRaises(GenesisRejected):
            inspect(self.source,self.vocab,partition="production")

    def test_reproducible_source_vocabulary(self):
        rebuilt=build_vocabulary(self.source,self.policy)
        self.assertEqual(rebuilt.digest,self.vocab.digest)
        self.assertEqual(rebuilt.entries,self.vocab.entries)


if __name__=="__main__":
    unittest.main()
