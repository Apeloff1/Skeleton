import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import DevicePolicy, GenerationConfig, NativeLLMRuntime, RuntimeContractError, RuntimeLimits


class TestNativeLLMEndToEnd(unittest.TestCase):
    def runtime(self, *, ctx=12):
        model = TinyTransformer(
            vocab=("the", "model", "runs", "locally", "with", "cache", "replay", "text"),
            dim=16,
            ctx=ctx,
            seed=20261007,
            n_heads=4,
            n_layers=3,
            d_ff=32,
        )
        return NativeLLMRuntime(model, device_policy=DevicePolicy("cpu"))

    def test_text_to_tokens_to_transformer_to_text_is_executable(self):
        runtime = self.runtime()
        prompt = "the model runs locally"
        encoded = runtime.encode(prompt)
        self.assertGreater(len(encoded.token_ids), 0)
        result = runtime.generate(
            prompt,
            GenerationConfig(max_new_tokens=4, temperature=0.0, seed=17),
        )
        self.assertEqual(result.prompt_sequence, encoded)
        self.assertEqual(len(result.generated_ids), 4)
        self.assertEqual(result.text, runtime.decode_ids(result.generated_ids))
        self.assertEqual(result.usage.generated_tokens, 4)
        self.assertEqual(result.events[-1].kind, "completed")

    def test_incremental_kv_path_matches_reference_decode(self):
        cached = self.runtime(ctx=8)
        reference = NativeLLMRuntime(
            TinyTransformer.from_snapshot(cached.model.snapshot()),
            device_policy=DevicePolicy("cpu"),
        )
        config = GenerationConfig(max_new_tokens=8, temperature=0.0, seed=5)
        left = cached.generate("the model runs", config)
        right = reference.generate(
            "the model runs",
            GenerationConfig(
                max_new_tokens=8,
                temperature=0.0,
                seed=5,
                use_cache=False,
            ),
        )
        self.assertEqual(left.generated_ids, right.generated_ids)
        self.assertEqual(left.output_digest, right.output_digest)
        self.assertGreater(left.usage.kv_peak_bytes, 0)
        self.assertEqual(right.usage.kv_peak_bytes, 0)

    def test_seeded_sampling_replay_survives_checkpoint_restore(self):
        runtime = self.runtime()
        config = GenerationConfig(
            max_new_tokens=6,
            temperature=0.75,
            top_k=5,
            top_p=0.9,
            seed=99173,
        )
        original = runtime.generate("the model", config)
        restored = NativeLLMRuntime.restore_json(
            runtime.checkpoint_json(),
            device_policy=DevicePolicy("cpu"),
        )
        replayed = restored.replay(original.replay_receipt, "the model", config)
        self.assertEqual(replayed.generated_ids, original.generated_ids)
        self.assertEqual(replayed.output_digest, original.output_digest)
        self.assertEqual(restored.model_digest, runtime.model_digest)
        self.assertEqual(restored.tokenizer.digest, runtime.tokenizer.digest)

    def test_memory_admission_is_fail_closed_before_decode(self):
        model = self.runtime(ctx=8).model
        baseline = NativeLLMRuntime(model)
        per_token = baseline.estimate_kv_bytes(1)
        limited = NativeLLMRuntime(
            TinyTransformer.from_snapshot(model.snapshot()),
            limits=RuntimeLimits(
                max_context=8,
                max_new_tokens=8,
                max_total_tokens=16,
                max_model_bytes=2**30,
                max_kv_bytes=per_token * 8,
                max_batch_size=4,
                max_batch_tokens=32,
                max_checkpoint_bytes=20_000_000,
            ),
        )
        result = limited.generate(
            "the model",
            GenerationConfig(max_new_tokens=2, temperature=0.0),
        )
        self.assertLessEqual(result.usage.kv_peak_bytes, limited.limits.max_kv_bytes)

        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime(
                TinyTransformer.from_snapshot(model.snapshot()),
                limits=RuntimeLimits(
                    max_context=8,
                    max_new_tokens=8,
                    max_total_tokens=16,
                    max_model_bytes=2**30,
                    max_kv_bytes=per_token * 8 - 1,
                    max_batch_size=4,
                    max_batch_tokens=32,
                    max_checkpoint_bytes=20_000_000,
                ),
            )

    def test_health_snapshot_binds_portability_and_resource_identity(self):
        runtime = self.runtime()
        health = runtime.health_snapshot()
        self.assertEqual(health["device"]["requested"], "cpu")
        self.assertEqual(health["device"]["actual"], "cpu")
        self.assertFalse(health["device"]["degraded"])
        self.assertEqual(health["model_digest"], runtime.model_digest)
        self.assertEqual(health["tokenizer_digest"], runtime.tokenizer.digest)
        self.assertEqual(health["architecture_digest"], runtime.architecture.digest)
        self.assertGreater(health["model_bytes"], 0)
        self.assertGreater(health["kv_bytes_per_token"], 0)


if __name__ == "__main__":
    unittest.main()
