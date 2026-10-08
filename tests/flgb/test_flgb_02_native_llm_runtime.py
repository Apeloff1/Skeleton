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

class TestNativeLLMRuntime(unittest.TestCase):
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

    def test_architecture_is_real_transformer_shape(self):
        runtime = self.runtime()
        architecture = runtime.architecture
        self.assertEqual(architecture.dim, 8)
        self.assertEqual(architecture.context, 8)
        self.assertEqual(architecture.heads, 2)
        self.assertEqual(architecture.layers, 2)
        self.assertEqual(architecture.feed_forward, 16)
        self.assertIn("rope", architecture.positional)
        health = runtime.health_snapshot()
        self.assertEqual(health["model_digest"], runtime.model_digest)
        self.assertEqual(
            health["tokenizer_digest"],
            runtime.tokenizer.digest,
        )
        self.assertGreater(health["model_bytes"], 0)
        self.assertGreater(health["kv_bytes_per_token"], 0)

    def test_generation_returns_only_new_tokens(self):
        runtime = self.runtime()
        prompt = runtime.encode("hello world")
        result = runtime.generate(
            "hello world",
            GenerationConfig(
                max_new_tokens=3,
                seed=3,
                temperature=0.0,
            ),
        )
        self.assertEqual(result.prompt_sequence, prompt)
        self.assertEqual(len(result.generated_ids), 3)
        self.assertEqual(len(result.generated_tokens), 3)
        self.assertEqual(
            result.usage.total_tokens,
            len(prompt.token_ids) + 3,
        )
        self.assertEqual(result.finish_reason, "length")
        record = result.to_record()
        self.assertEqual(
            record["generated_token_ids"],
            list(result.generated_ids),
        )
        self.assertEqual(record["output_digest"], result.output_digest)

    def test_stream_has_admission_prompt_tokens_completion(self):
        runtime = self.runtime()
        stream = runtime.stream(
            "hello world",
            GenerationConfig(
                max_new_tokens=2,
                seed=2,
                temperature=0.0,
            ),
        )
        events = list(stream)
        self.assertIsNotNone(stream.result)
        self.assertEqual(
            [event.kind for event in events[:2]],
            ["admitted", "prompt"],
        )
        self.assertEqual(events[-1].kind, "completed")
        self.assertEqual(
            tuple(
                event.token_id
                for event in events
                if event.kind == "token"
            ),
            stream.result.generated_ids,
        )

    def test_cached_and_uncached_greedy_decode_match(self):
        left = self.runtime(ctx=6)
        right = NativeLLMRuntime(
            TinyTransformer.from_snapshot(left.model.snapshot())
        )
        cached = left.generate(
            "hello world again",
            GenerationConfig(
                max_new_tokens=6,
                temperature=0.0,
                use_cache=True,
            ),
        )
        uncached = right.generate(
            "hello world again",
            GenerationConfig(
                max_new_tokens=6,
                temperature=0.0,
                use_cache=False,
            ),
        )
        self.assertEqual(cached.generated_ids, uncached.generated_ids)
        self.assertEqual(cached.text, uncached.text)
        self.assertGreater(cached.usage.kv_peak_bytes, 0)
        self.assertEqual(uncached.usage.kv_peak_bytes, 0)
        self.assertGreaterEqual(cached.usage.cache_resets, 1)

    def test_seeded_sampling_replays(self):
        runtime = self.runtime()
        config = GenerationConfig(
            max_new_tokens=5,
            seed=991,
            temperature=0.9,
            top_k=4,
            top_p=0.8,
        )
        first = runtime.generate("hello world", config)
        replay = runtime.replay(
            first.replay_receipt,
            "hello world",
            config,
        )
        self.assertEqual(replay.generated_ids, first.generated_ids)
        self.assertEqual(replay.output_digest, first.output_digest)
        with self.assertRaises(ReplayMismatch):
            runtime.replay(
                first.replay_receipt,
                "hello world",
                GenerationConfig(
                    max_new_tokens=5,
                    seed=992,
                    temperature=0.9,
                    top_k=4,
                    top_p=0.8,
                ),
            )

    def test_stop_token_terminates_decode(self):
        runtime = self.runtime()
        first = runtime.generate(
            "hello world",
            GenerationConfig(
                max_new_tokens=1,
                temperature=0.0,
            ),
        )
        stop_id = first.generated_ids[0]
        stopped = runtime.generate(
            "hello world",
            GenerationConfig(
                max_new_tokens=6,
                temperature=0.0,
                stop_token_ids=(stop_id,),
            ),
        )
        self.assertEqual(stopped.finish_reason, "stop_token")
        self.assertEqual(stopped.generated_ids, (stop_id,))
        self.assertIn(
            "stopped",
            [event.kind for event in stopped.events],
        )

    def test_checkpoint_round_trip_and_tamper_rejection(self):
        runtime = self.runtime()
        config = GenerationConfig(
            max_new_tokens=4,
            seed=42,
            temperature=0.0,
        )
        before = runtime.generate("hello world", config)
        checkpoint = runtime.checkpoint()
        restored = NativeLLMRuntime.restore(
            checkpoint,
            device_policy=DevicePolicy("cpu"),
        )
        after = restored.generate("hello world", config)
        self.assertEqual(restored.model_digest, runtime.model_digest)
        self.assertEqual(
            restored.tokenizer.digest,
            runtime.tokenizer.digest,
        )
        self.assertEqual(after.generated_ids, before.generated_ids)
        self.assertEqual(after.output_digest, before.output_digest)
        from_json = NativeLLMRuntime.restore_json(
            runtime.checkpoint_json(),
            device_policy=DevicePolicy("cpu"),
        )
        self.assertEqual(from_json.model_digest, runtime.model_digest)

        tampered = copy.deepcopy(checkpoint)
        tampered["model"]["E"][0][0] += 1.0
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(tampered)

    def test_model_and_bpe_mutation_require_readmission(self):
        model = self.model()
        bpe = BytePairEncoder(merges=8)
        bpe.fit(("hello world", "hello again", "small runtime"))
        model.bpe = bpe
        runtime = NativeLLMRuntime(model)
        old = runtime.model_digest

        runtime.model.bout[0] += 0.25
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello",
                GenerationConfig(max_new_tokens=1),
            )
        self.assertNotEqual(old, runtime.refresh_model_identity())

        runtime.model.bpe.merges.append(("x", "y", "xy"))
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello",
                GenerationConfig(max_new_tokens=1),
            )

    def test_context_total_model_and_kv_budgets_fail_closed(self):
        runtime = NativeLLMRuntime(
            self.model(ctx=4),
            limits=RuntimeLimits(
                max_context=4,
                max_new_tokens=3,
                max_total_tokens=5,
                max_model_bytes=2**30,
                max_kv_bytes=2**30,
                max_batch_size=4,
                max_batch_tokens=20,
                max_checkpoint_bytes=20_000_000,
            ),
        )
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello world again small runtime",
                GenerationConfig(max_new_tokens=1),
            )
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello world again",
                GenerationConfig(max_new_tokens=3),
            )
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello",
                GenerationConfig(max_new_tokens=4),
            )

        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime(
                self.model(ctx=4),
                limits=RuntimeLimits(
                    max_context=4,
                    max_new_tokens=2,
                    max_total_tokens=6,
                    max_model_bytes=2**30,
                    max_kv_bytes=1,
                    max_batch_size=4,
                    max_batch_tokens=20,
                    max_checkpoint_bytes=20_000_000,
                ),
            )

    def test_replay_receipt_and_checkpoint_envelopes_fail_closed(self):
        runtime = self.runtime()
        result = runtime.generate(
            "hello world",
            GenerationConfig(max_new_tokens=1, seed=4, temperature=0.0),
        )
        receipt = result.replay_receipt
        with self.assertRaises(RuntimeContractError):
            ReplayReceipt(
                model_digest="bad",
                tokenizer_digest=receipt.tokenizer_digest,
                architecture_digest=receipt.architecture_digest,
                request_digest=receipt.request_digest,
                output_digest=receipt.output_digest,
                config_digest=receipt.config_digest,
                device_digest=receipt.device_digest,
                seed=receipt.seed,
            )
        with self.assertRaises(RuntimeContractError):
            ReplayReceipt(
                model_digest=receipt.model_digest,
                tokenizer_digest=receipt.tokenizer_digest,
                architecture_digest=receipt.architecture_digest,
                request_digest=receipt.request_digest,
                output_digest=receipt.output_digest,
                config_digest=receipt.config_digest,
                device_digest=receipt.device_digest,
                seed=receipt.seed,
                schema="unsupported",
            )

        checkpoint = copy.deepcopy(runtime.checkpoint())
        checkpoint["unexpected"] = True
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(checkpoint)

    def test_batch_and_sampling_contracts(self):
        runtime = self.runtime()
        config = GenerationConfig(
            max_new_tokens=2,
            seed=1,
            temperature=0.0,
        )
        results = runtime.generate_batch(
            (
                BatchGenerationRequest("a", "hello", config),
                BatchGenerationRequest("b", "world", config),
            )
        )
        self.assertEqual(
            [item.request_id for item in results],
            ["a", "b"],
        )
        with self.assertRaises(RuntimeContractError):
            runtime.generate_batch(
                (
                    BatchGenerationRequest("same", "hello", config),
                    BatchGenerationRequest("same", "world", config),
                )
            )
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello",
                GenerationConfig(max_new_tokens=1, top_p=0.0),
            )
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello",
                GenerationConfig(
                    max_new_tokens=1,
                    top_k=runtime.tokenizer.vocab_size + 1,
                ),
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


if __name__ == "__main__":
    unittest.main()
