from __future__ import annotations

import unittest

from skeleton.ai.model_runtime.tokenization import (
    ModelRuntimeError,
    NativeTokenizer,
    TokenSequence,
)
from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.transformer import TinyTransformer

D = "a" * 64


class TestTokenization(unittest.TestCase):
    def test_identity_and_bounds(self):
        seq = TokenSequence(D, (1, 2, 3), D)
        self.assertEqual(len(seq.digest), 64)
        with self.assertRaises(ModelRuntimeError):
            TokenSequence(D, (-1,), D)

    def test_model_bound_tokenizer_has_stable_identity_and_manifest(self):
        model = TinyTransformer(
            vocab=("alpha", "beta", "hello", "world"),
            dim=8,
            ctx=8,
            seed=7,
            n_heads=2,
        )
        tokenizer = NativeTokenizer(model)
        sequence = tokenizer.encode("hello world")
        self.assertEqual(sequence.tokenizer_digest, tokenizer.digest)
        self.assertEqual(sequence.token_ids, tuple(model._ids("hello world")))
        manifest = tokenizer.manifest()
        self.assertEqual(len(manifest.tokens), len(model.itos))
        self.assertEqual(manifest.special_tokens["unk"], model.unk)
        self.assertEqual(manifest.tokens[model.stoi["hello"]][0], "hello")

    def test_decode_rejects_unknown_ids(self):
        model = TinyTransformer(vocab=("hello", "world"), dim=8, ctx=8)
        tokenizer = NativeTokenizer(model)
        with self.assertRaises(ModelRuntimeError):
            tokenizer.decode_ids((len(model.itos),))
        with self.assertRaises(ModelRuntimeError):
            tokenizer.decode_ids((True,))

    def test_bpe_rules_change_tokenizer_identity(self):
        model = TinyTransformer(
            vocab=("alpha", "beta", "hello", "world"),
            dim=8,
            ctx=8,
            seed=11,
        )
        plain = NativeTokenizer(model).digest
        bpe = BytePairEncoder(merges=8)
        bpe.fit(("hello world", "hello hello world"))
        model.bpe = bpe
        bound = NativeTokenizer(model)
        self.assertNotEqual(bound.digest, plain)
        self.assertEqual(bound.state.bpe, bpe.snapshot())

    def test_word_vocab_does_not_use_bpe_decode_without_piece_coverage(self):
        model = TinyTransformer(
            vocab=("hello", "world"),
            dim=8,
            ctx=8,
            seed=13,
        )
        bpe = BytePairEncoder(merges=8)
        bpe.fit(("hello world", "hello hello"))
        model.bpe = bpe
        tokenizer = NativeTokenizer(model)
        ids = (model.stoi["hello"], model.stoi["world"])
        self.assertEqual(tokenizer.decode_ids(ids), "hello world")

    def test_encode_rejects_non_integer_model_token_ids(self):
        class BadModel:
            itos = ["__unk__", "hello"]
            stoi = {"__unk__": 0, "hello": 1}
            unk = 0

            def _ids(self, text):
                return ["1"]

        tokenizer = NativeTokenizer(BadModel())
        with self.assertRaises(ModelRuntimeError):
            tokenizer.encode_ids("hello")

    def test_encode_many_preserves_order_and_source_identity(self):
        model = TinyTransformer(
            vocab=("alpha", "beta", "hello", "world"),
            dim=8,
            ctx=8,
        )
        tokenizer = NativeTokenizer(model)
        batch = tokenizer.encode_many(("hello", "world", "alpha beta"))
        self.assertEqual(len(batch), 3)
        self.assertEqual(batch[0].token_ids, tokenizer.encode("hello").token_ids)
        self.assertNotEqual(batch[0].source_text_digest, batch[1].source_text_digest)


if __name__ == "__main__":
    unittest.main()
