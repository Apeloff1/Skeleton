import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.tokenization import (
    NativeTokenizer,
    StreamingTextFeed,
    TokenizerContractError,
    TokenizerLimits,
    batch_token_windows,
    deserialize_token_sequence,
    iter_context_windows,
    serialize_token_sequence,
)


class TestNativeTokenizationPipeline(unittest.TestCase):
    def model(self):
        return TinyTransformer(
            vocab=("hello", "world", "again", "small", "runtime"),
            dim=8,
            ctx=8,
            seed=7,
            n_heads=2,
            n_layers=2,
            d_ff=16,
        )

    def test_chunk_boundaries_do_not_change_tokens(self):
        tokenizer = NativeTokenizer(self.model())
        direct = tokenizer.encode_sequence("hello world again")
        feed = StreamingTextFeed()
        feed.push("hel")
        feed.push("lo world ")
        feed.push("again")
        self.assertEqual(feed.finalize(tokenizer), direct)
        self.assertTrue(feed.closed)
        with self.assertRaises(TokenizerContractError):
            feed.push("late")

    def test_identity_manifest_and_source_digest_are_stable(self):
        model = self.model()
        left = NativeTokenizer(model)
        right = NativeTokenizer(model)
        self.assertEqual(left.digest, right.digest)
        self.assertEqual(
            left.vocabulary_manifest.digest,
            right.vocabulary_manifest.digest,
        )
        seq = left.encode_sequence("hello world")
        self.assertEqual(seq.tokenizer_digest, left.digest)
        self.assertEqual(len(seq.source_text_digest), 64)

    def test_canonical_serialization_round_trip(self):
        tokenizer = NativeTokenizer(self.model())
        seq = tokenizer.encode_sequence("hello world")
        raw = serialize_token_sequence(seq)
        self.assertEqual(raw, serialize_token_sequence(seq))
        self.assertEqual(deserialize_token_sequence(raw), seq)
        with self.assertRaises(TokenizerContractError):
            deserialize_token_sequence(b'{"token_ids":[]}')
        with self.assertRaises(TokenizerContractError):
            deserialize_token_sequence(b"not-json")

    def test_context_windows_and_batches_are_deterministic(self):
        tokenizer = NativeTokenizer(self.model())
        seq = tokenizer.encode_sequence(
            "hello world again small runtime"
        )
        windows = tuple(
            iter_context_windows(seq, context_size=3, stride=2)
        )
        self.assertEqual(
            [(item.start, item.stop) for item in windows],
            [(0, 3), (2, 5)],
        )
        self.assertTrue(
            all(item.source_sequence_digest == seq.digest for item in windows)
        )
        batches = batch_token_windows(
            windows,
            max_batch_size=1,
            max_tokens_per_batch=3,
        )
        self.assertEqual([batch.total_tokens for batch in batches], [3, 3])
        self.assertEqual(
            batches,
            batch_token_windows(
                windows,
                max_batch_size=1,
                max_tokens_per_batch=3,
            ),
        )

    def test_feed_and_decode_budgets_fail_closed(self):
        limits = TokenizerLimits(
            max_chars=5,
            max_chunks=2,
            max_chunk_chars=4,
            max_tokens=8,
        )
        tokenizer = NativeTokenizer(self.model(), limits=limits)
        with self.assertRaises(TokenizerContractError):
            tokenizer.encode_sequence("hello!")
        feed = StreamingTextFeed(limits=limits)
        feed.push("hell")
        with self.assertRaises(TokenizerContractError):
            feed.push("xx")
        with self.assertRaises(TokenizerContractError):
            tokenizer.decode_ids((tokenizer.vocab_size,))

    def test_stride_and_window_budget_reject_invalid_shapes(self):
        tokenizer = NativeTokenizer(self.model())
        seq = tokenizer.encode_sequence("hello world again")
        with self.assertRaises(TokenizerContractError):
            tuple(iter_context_windows(seq, context_size=2, stride=3))
        windows = tuple(iter_context_windows(seq, context_size=2))
        with self.assertRaises(TokenizerContractError):
            batch_token_windows(
                windows,
                max_batch_size=2,
                max_tokens_per_batch=1,
            )


if __name__ == "__main__":
    unittest.main()
