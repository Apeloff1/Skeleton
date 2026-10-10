import copy
import unittest

from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import (
    BatchGenerationRequest,
    DevicePolicy,
    GenerationConfig,
    NativeLLMRuntime,
    ReplayMismatch,
    ReplayReceipt,
    RuntimeContractError,
    RuntimeLimits,
    StreamingTextFeed,
    TokenSequence,
)



def runtime_kv_budget(model):
    return model.ctx * model.n_layers * model.dim * 2 * 8 + model.ctx * 8

class TestNativeSequenceGraph(unittest.TestCase):
    def model(self, *, ctx=8, seed=11):
        return TinyTransformer(
            vocab=("hello", "world", "again", "small", "runtime", "token"),
            dim=8,
            ctx=ctx,
            seed=seed,
            n_heads=2,
            n_layers=2,
            d_ff=16,
        )

    def runtime(self, *, ctx=8):
        return NativeLLMRuntime(
            self.model(ctx=ctx),
            device_policy=DevicePolicy("cpu"),
        )

    def test_streaming_text_feed_executes_without_retokenization_boundary(self):
        runtime = self.runtime()
        feed = StreamingTextFeed()
        feed.push("hello ")
        feed.push("world")
        result = runtime.generate_feed(
            feed,
            GenerationConfig(max_new_tokens=3, seed=17, temperature=0.0),
        )
        direct = runtime.generate(
            "hello world",
            GenerationConfig(max_new_tokens=3, seed=17, temperature=0.0),
        )
        self.assertTrue(feed.closed)
        self.assertEqual(result.prompt_sequence, direct.prompt_sequence)
        self.assertEqual(result.generated_ids, direct.generated_ids)
        self.assertEqual(result.output_digest, direct.output_digest)

    def test_pretokenized_sequence_executes_and_preserves_identity(self):
        runtime = self.runtime()
        sequence = runtime.encode("hello world")
        result = runtime.generate_sequence(
            sequence,
            GenerationConfig(max_new_tokens=2, seed=5, temperature=0.0),
        )
        self.assertIs(result.prompt_sequence, sequence)
        self.assertEqual(result.replay_receipt.tokenizer_digest, sequence.tokenizer_digest)
        self.assertEqual(result.usage.prompt_tokens, len(sequence.token_ids))

    def test_pretokenized_sequence_rejects_foreign_tokenizer_and_vocab(self):
        runtime = self.runtime()
        sequence = runtime.encode("hello")
        foreign = TokenSequence(
            "0" * 64,
            sequence.token_ids,
            sequence.source_text_digest,
        )
        with self.assertRaises(RuntimeContractError):
            runtime.generate_sequence(foreign, GenerationConfig(max_new_tokens=1))
        invalid = TokenSequence(
            sequence.tokenizer_digest,
            (runtime.tokenizer.vocab_size,),
            sequence.source_text_digest,
        )
        with self.assertRaises(RuntimeContractError):
            runtime.generate_sequence(invalid, GenerationConfig(max_new_tokens=1))


    def test_inference_graph_cached_uncached_and_checkpoint_parity(self):
        runtime = self.runtime(ctx=8)
        prompt = "hello world again"
        cached = runtime.infer_text(prompt, use_cache=True)
        uncached = runtime.infer_text(prompt, use_cache=False)
        self.assertEqual(len(cached.logits), runtime.tokenizer.vocab_size)
        self.assertEqual(cached.argmax_token_id, uncached.argmax_token_id)
        for left, right in zip(cached.logits, uncached.logits):
            self.assertAlmostEqual(left, right, places=8)
        restored = NativeLLMRuntime.restore(runtime.checkpoint())
        after = restored.infer_text(prompt, use_cache=False)
        self.assertEqual(uncached.digest, after.digest)

    def test_inference_graph_context_and_identity_fail_closed(self):
        runtime = self.runtime(ctx=4)
        with self.assertRaises(RuntimeContractError):
            runtime.infer_text("hello world again small runtime")
        with self.assertRaises(RuntimeContractError):
            runtime.infer_sequence(runtime.encode("hello"), use_cache="yes")
        sequence = runtime.encode("hello")
        foreign = TokenSequence("0" * 64, sequence.token_ids, sequence.source_text_digest)
        with self.assertRaises(RuntimeContractError):
            runtime.infer_sequence(foreign)
        runtime.model.bout[0] += 0.1
        with self.assertRaises(RuntimeContractError):
            runtime.infer_sequence(sequence)

    def test_token_sequence_stream_matches_text_stream(self):
        runtime = self.runtime()
        cfg = GenerationConfig(max_new_tokens=3, temperature=0.0, seed=19)
        direct = runtime.generate("hello world", cfg)
        sequence = runtime.encode("hello world")
        tokenized = runtime.generate_sequence(sequence, cfg)
        self.assertEqual(direct.generated_ids, tokenized.generated_ids)
        self.assertEqual(direct.output_digest, tokenized.output_digest)
        self.assertEqual(
            [(event.kind, event.token_id) for event in direct.events],
            [(event.kind, event.token_id) for event in tokenized.events],
        )


    def test_token_and_text_decoders_match_sampling_stop_and_zero_budget(self):
        runtime = self.runtime(ctx=8)
        prompt = "hello world"
        sequence = runtime.encode(prompt)
        first = runtime.generate(prompt, GenerationConfig(max_new_tokens=1, temperature=0.0))
        for config in (
            GenerationConfig(max_new_tokens=0, temperature=0.0),
            GenerationConfig(max_new_tokens=5, seed=72, temperature=0.9, top_k=4, top_p=0.85),
            GenerationConfig(max_new_tokens=5, seed=72, temperature=0.0, stop_token_ids=first.generated_ids),
            GenerationConfig(max_new_tokens=6, seed=17, temperature=0.0, use_cache=False),
        ):
            direct = runtime.generate(prompt, config)
            tokenized = runtime.generate_sequence(sequence, config)
            self.assertEqual(direct.generated_ids, tokenized.generated_ids)
            self.assertEqual(direct.text, tokenized.text)
            self.assertEqual(direct.finish_reason, tokenized.finish_reason)
            self.assertEqual(direct.usage, tokenized.usage)
            self.assertEqual(direct.replay_receipt, tokenized.replay_receipt)
            self.assertEqual(direct.events, tokenized.events)

    def test_token_sequence_budget_and_model_mutation_fail_closed(self):
        runtime = self.runtime(ctx=4)
        oversized = runtime.encode("hello world again small runtime")
        with self.assertRaises(RuntimeContractError):
            runtime.generate_sequence(oversized, GenerationConfig(max_new_tokens=1))
        sequence = runtime.encode("hello")
        runtime.model.bout[0] += 0.125
        with self.assertRaises(RuntimeContractError):
            runtime.generate_sequence(sequence, GenerationConfig(max_new_tokens=1))


    def test_refresh_identity_rejects_model_context_shrink_atomically(self):
        runtime = self.runtime(ctx=8)
        original_digest = runtime.model_digest
        original_architecture = runtime.architecture
        original_tokenizer = runtime.tokenizer
        runtime.model.ctx = 4
        with self.assertRaises(RuntimeContractError):
            runtime.refresh_model_identity()
        self.assertEqual(runtime.model_digest, original_digest)
        self.assertIs(runtime.architecture, original_architecture)
        self.assertIs(runtime.tokenizer, original_tokenizer)

    def test_refresh_identity_rejects_kv_budget_growth_atomically(self):
        model = self.model(ctx=8)
        runtime = NativeLLMRuntime(
            model,
            limits=RuntimeLimits(
                max_context=8,
                max_new_tokens=3,
                max_total_tokens=12,
                max_model_bytes=2**30,
                max_kv_bytes=runtime_kv_budget(model),
                max_batch_size=4,
                max_batch_tokens=32,
                max_checkpoint_bytes=20_000_000,
            ),
        )
        original_digest = runtime.model_digest
        original_architecture = runtime.architecture
        original_tokenizer = runtime.tokenizer
        runtime.model.n_layers += 1
        with self.assertRaises(RuntimeContractError):
            runtime.refresh_model_identity()
        self.assertEqual(runtime.model_digest, original_digest)
        self.assertIs(runtime.architecture, original_architecture)
        self.assertIs(runtime.tokenizer, original_tokenizer)


    def test_generation_rejects_nonfinite_transformer_logits(self):
        runtime = self.runtime()
        original = runtime.model._logits_window
        try:
            runtime.model._logits_window = lambda window, cache: [float("nan")] * runtime.tokenizer.vocab_size
            with self.assertRaisesRegex(RuntimeContractError, "non-finite logits"):
                runtime.generate("hello", GenerationConfig(max_new_tokens=1))
        finally:
            runtime.model._logits_window = original

    def test_generation_rejects_invalid_transformer_logits_shape(self):
        runtime = self.runtime()
        original = runtime.model._logits_window
        try:
            runtime.model._logits_window = lambda window, cache: [0.0]
            with self.assertRaisesRegex(RuntimeContractError, "invalid logits shape"):
                runtime.generate("hello", GenerationConfig(max_new_tokens=1))
        finally:
            runtime.model._logits_window = original




if __name__ == "__main__":
    unittest.main()
