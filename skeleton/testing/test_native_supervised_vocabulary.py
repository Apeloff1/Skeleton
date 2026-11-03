"""Native tokenizer fitted on framed training pairs only, not evaluation fixtures."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.cortex.port import tokens
from skeleton.ai.runtime.operational_ai.native_supervised.source import prepare_source
from skeleton.ai.runtime.operational_ai.native_supervised.policy import SupervisedPolicy
from skeleton.ai.runtime.operational_ai.native_supervised.vocabulary import build_aligned_vocabulary
from skeleton.ai.runtime.operational_ai.native_supervised.frames import paired_train
from skeleton.ai.runtime.operational_ai.native_supervised.errors import SupervisedRejected


class TestNativeSupervisedVocab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=prepare_source()
        cls.policy=SupervisedPolicy(operator_approved=True)
        cls.vocab=build_aligned_vocabulary(cls.source,cls.policy)

    def test_train_only_fit_provenance(self):
        self.assertEqual(self.vocab.observed_documents,432)
        report=self.vocab.record()
        self.assertFalse(report["fit_validation"])
        self.assertFalse(report["fit_holdout"])
        self.assertFalse(report["fit_challenges"])

    def test_roles_present_in_vocabulary(self):
        for term in ("message","role","assistant","user","bytes"):
            self.assertIn(term,self.vocab.terms)

    def test_every_training_token_known(self):
        known=set(self.vocab.terms)
        for pair in paired_train(self.source.groups):
            observed=tokens(pair.prompt+" "+pair.completion)
            self.assertTrue(set(observed)<=known)

    def test_sorted_unique_native_terms(self):
        self.assertEqual(self.vocab.terms,tuple(sorted(set(self.vocab.terms))))

    def test_small_vocab_limit_denied(self):
        with self.assertRaises(SupervisedRejected):
            build_aligned_vocabulary(self.source,
                                     replace(self.policy,max_vocabulary=64))

    def test_source_hash_changes_vocabulary_stamp(self):
        self.assertEqual(self.vocab.corpus_sha256,self.source.corpus_sha256)
        self.assertEqual(len(self.vocab.schema_sha256),64)

    def test_rebuilding_same_source_is_deterministic(self):
        other=build_aligned_vocabulary(self.source,self.policy)
        self.assertEqual(other.terms,self.vocab.terms)
        self.assertEqual(other.schema_sha256,self.vocab.schema_sha256)


if __name__=="__main__":
    unittest.main()
