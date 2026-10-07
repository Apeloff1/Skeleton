from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import unittest

from skeleton.ai.model_runtime.native_llm_runtime import (
    InferenceReceipt,
    InferenceRequest,
    NativeLLMRuntime,
    RuntimeContractError,
    RuntimeLimits,
    SamplingConfig,
)
from skeleton.cortex.bpe import BytePairEncoder
from skeleton.cortex.transformer import TinyTransformer


def _runtime(*, limits: RuntimeLimits | None = None) -> NativeLLMRuntime:
    model = TinyTransformer(
        vocab=("alpha", "beta", "delta", "gamma", "hello", "world"),
        dim=8,
        ctx=8,
        seed=17,
        n_heads=2,
        n_layers=2,
        d_ff=16,
        norm="rms",
        ffn_kind="swiglu",
    )
    return NativeLLMRuntime(
        model,
        limits=limits or RuntimeLimits(
            max_context_tokens=8,
            max_output_tokens=8,
            max_batch_size=4,
            max_batch_tokens=64,
            max_model_bytes=16 * 1024 * 1024,
            max_kv_bytes=16 * 1024 * 1024,
            trace_capacity=256,
        ),
    )


def _redigest_checkpoint(checkpoint):
    body = dict(checkpoint)
    body.pop("checkpoint_digest", None)
    raw = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    body["checkpoint_digest"] = sha256(raw).hexdigest()
    return body


class TestNativeLLMRuntime(unittest.TestCase):
    def test_text_to_token_to_embedding_to_logits_is_executable(self):
        runtime = _runtime()
        sequence = runtime.tokenize("hello world")
        self.assertEqual(sequence.tokenizer_digest, runtime.tokenizer_digest)
        self.assertGreaterEqual(len(sequence.token_ids), 1)
        embeddings = runtime.embed_ids(sequence.token_ids)
        self.assertEqual(len(embeddings), len(sequence.token_ids))
        self.assertTrue(
            all(len(row) == runtime.model.dim for row in embeddings)
        )
        forward = runtime.forward("hello world")
        self.assertEqual(forward.token_sequence.digest, sequence.digest)
        self.assertEqual(len(forward.last_hidden), runtime.model.dim)
        self.assertEqual(len(forward.logits), len(runtime.model.itos))
        self.assertAlmostEqual(sum(forward.probabilities), 1.0, places=9)
        graph = runtime.execution_graph()
        self.assertIn("tokenize", graph)
        self.assertIn("layer[0].causal-mha-rope", graph)
        self.assertIn("unembed", graph)

    def test_embedding_includes_position_and_enforces_bounds(self):
        runtime = _runtime()
        token_id = runtime.model.stoi["hello"]
        rows = runtime.embed_ids((token_id, token_id))
        expected0 = tuple(
            runtime.model.E[token_id][i] + runtime.model.P[0][i]
            for i in range(runtime.model.dim)
        )
        expected1 = tuple(
            runtime.model.E[token_id][i] + runtime.model.P[1][i]
            for i in range(runtime.model.dim)
        )
        self.assertEqual(rows[0], expected0)
        self.assertEqual(rows[1], expected1)
        with self.assertRaises(RuntimeContractError):
            runtime.embed_ids((len(runtime.model.itos),))

    def test_generation_returns_continuation_not_prompt_prefix(self):
        runtime = _runtime()
        cfg = SamplingConfig(
            max_new_tokens=4,
            seed=101,
            temperature=0.9,
            top_k=3,
        )
        result = runtime.generate("hello world", cfg)
        self.assertEqual(result.prompt_ids, runtime.encode("hello world"))
        self.assertEqual(len(result.generated_token_ids), 4)
        self.assertEqual(len(result.generated_tokens), 4)
        self.assertEqual(
            result.text,
            runtime.decode(result.generated_token_ids),
        )
        self.assertEqual(
            result.receipt.generated_token_ids,
            result.generated_token_ids,
        )
        self.assertEqual(len(result.receipt.semantic_digest), 64)

    def test_cached_and_uncached_decode_are_semantically_equivalent(self):
        runtime = _runtime()
        cached = runtime.generate(
            "hello world",
            SamplingConfig(
                max_new_tokens=5,
                seed=9,
                temperature=0.8,
                top_k=4,
                use_cache=True,
            ),
        )
        uncached = runtime.generate(
            "hello world",
            SamplingConfig(
                max_new_tokens=5,
                seed=9,
                temperature=0.8,
                top_k=4,
                use_cache=False,
            ),
        )
        self.assertEqual(
            cached.generated_token_ids,
            uncached.generated_token_ids,
        )
        self.assertEqual(cached.text, uncached.text)
        self.assertTrue(cached.receipt.cache_used)
        self.assertFalse(uncached.receipt.cache_used)

    def test_context_overflow_is_fail_closed_or_explicitly_truncated(self):
        runtime = _runtime()
        prompt = " ".join(["hello"] * 12)
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                prompt,
                SamplingConfig(
                    max_new_tokens=1,
                    context_policy="reject",
                ),
            )
        result = runtime.generate(
            prompt,
            SamplingConfig(
                max_new_tokens=1,
                seed=3,
                context_policy="truncate-left",
            ),
        )
        self.assertTrue(result.receipt.context_truncated)
        self.assertEqual(
            result.receipt.prompt_tokens,
            runtime.limits.max_context_tokens,
        )
        self.assertGreater(
            len(result.prompt_sequence.token_ids),
            result.receipt.prompt_tokens,
        )

    def test_sampling_and_stop_contracts_reject_invalid_values(self):
        with self.assertRaises(RuntimeContractError):
            SamplingConfig(temperature=0.0)
        with self.assertRaises(RuntimeContractError):
            SamplingConfig(top_p=1.1)
        with self.assertRaises(RuntimeContractError):
            SamplingConfig(context_policy="silent-truncate")
        runtime = _runtime()
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello",
                SamplingConfig(max_new_tokens=9),
            )
        with self.assertRaises(RuntimeContractError):
            runtime.generate(
                "hello",
                SamplingConfig(max_new_tokens=1, top_k=999),
            )

    def test_checkpoint_roundtrip_preserves_model_tokenizer_and_generation(self):
        runtime = _runtime()
        checkpoint = runtime.checkpoint()
        restored = NativeLLMRuntime.restore(checkpoint)
        self.assertEqual(restored.model_digest, runtime.model_digest)
        self.assertEqual(
            restored.tokenizer_digest,
            runtime.tokenizer_digest,
        )
        cfg = SamplingConfig(max_new_tokens=5, seed=77, top_k=4)
        left = runtime.generate("alpha beta", cfg)
        right = restored.generate("alpha beta", cfg)
        self.assertEqual(
            left.generated_token_ids,
            right.generated_token_ids,
        )
        self.assertEqual(left.text, right.text)

    def test_checkpoint_integrity_and_geometry_fail_closed(self):
        runtime = _runtime()
        tampered = deepcopy(runtime.checkpoint())
        tampered["model"]["E"][0][0] += 1.0
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(tampered)

        malformed = deepcopy(runtime.checkpoint())
        malformed["model"]["E"][0] = malformed["model"]["E"][0][:-1]
        malformed = _redigest_checkpoint(malformed)
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(malformed)

    def test_bpe_state_is_part_of_tokenizer_identity_and_checkpoint(self):
        runtime = _runtime()
        bpe = BytePairEncoder(merges=16)
        bpe.fit((
            "hello world",
            "hello hello world",
            "alpha beta gamma",
        ))
        runtime.model.bpe = bpe
        runtime = NativeLLMRuntime(
            runtime.model,
            limits=runtime.limits,
        )
        checkpoint = runtime.checkpoint()
        restored = NativeLLMRuntime.restore(checkpoint)
        self.assertEqual(
            restored.tokenizer_digest,
            runtime.tokenizer_digest,
        )
        self.assertTrue(hasattr(restored.model, "bpe"))
        self.assertEqual(
            restored.model.bpe.snapshot(),
            bpe.snapshot(),
        )

    def test_replay_binds_prompt_sampling_model_and_output(self):
        runtime = _runtime()
        cfg = SamplingConfig(
            max_new_tokens=3,
            seed=12,
            top_p=0.9,
        )
        first = runtime.generate("hello alpha", cfg)
        replay = runtime.replay(
            "hello alpha",
            cfg,
            first.receipt,
        )
        self.assertEqual(
            first.generated_token_ids,
            replay.generated_token_ids,
        )
        self.assertEqual(
            first.receipt.semantic_digest,
            replay.receipt.semantic_digest,
        )
        with self.assertRaises(RuntimeContractError):
            runtime.replay(
                "hello beta",
                cfg,
                first.receipt,
            )
        with self.assertRaises(RuntimeContractError):
            runtime.replay(
                "hello alpha",
                SamplingConfig(
                    max_new_tokens=3,
                    seed=13,
                    top_p=0.9,
                ),
                first.receipt,
            )

    def test_memory_admission_is_explicit_and_bounded(self):
        runtime = _runtime()
        report = runtime.memory_report()
        self.assertGreater(report.parameter_count, 0)
        self.assertEqual(
            report.total_numeric_bytes,
            report.numeric_model_bytes + report.kv_payload_bytes,
        )
        tiny = RuntimeLimits(
            max_context_tokens=8,
            max_output_tokens=4,
            max_batch_size=2,
            max_batch_tokens=32,
            max_model_bytes=8,
            max_kv_bytes=16 * 1024 * 1024,
        )
        model = TinyTransformer(
            vocab=("hello", "world"),
            dim=8,
            ctx=8,
            n_heads=2,
            n_layers=1,
            d_ff=8,
        )
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime(model, limits=tiny)

    def test_cpu_binding_and_unknown_device_policy(self):
        runtime = _runtime()
        report = runtime.bind_device(
            "cpu",
            allow_fallback=False,
        )
        self.assertEqual(report["actual"], "cpu")
        self.assertFalse(report["degraded"])
        with self.assertRaises(RuntimeContractError):
            runtime.bind_device("quantum")

    def test_batch_contract_is_bounded_ordered_and_unique(self):
        runtime = _runtime()
        cfg = SamplingConfig(max_new_tokens=2, seed=5)
        results = runtime.generate_batch((
            InferenceRequest("a", "hello", cfg),
            InferenceRequest("b", "world", cfg),
        ))
        self.assertEqual(len(results), 2)
        with self.assertRaises(RuntimeContractError):
            runtime.generate_batch((
                InferenceRequest("a", "hello", cfg),
                InferenceRequest("a", "world", cfg),
            ))

    def test_inference_receipt_roundtrip_is_strict_and_canonical(self):
        runtime = _runtime()
        result = runtime.generate(
            "hello world",
            SamplingConfig(max_new_tokens=2, seed=41),
        )
        payload = result.receipt.to_dict()
        restored = InferenceReceipt.from_dict(payload)
        self.assertEqual(restored, result.receipt)
        self.assertEqual(restored.audit_digest, result.receipt.audit_digest)
        drifted = dict(payload)
        drifted["unexpected"] = True
        with self.assertRaises(RuntimeContractError):
            InferenceReceipt.from_dict(drifted)
        coerced = dict(payload)
        coerced["prompt_tokens"] = str(payload["prompt_tokens"])
        with self.assertRaises(RuntimeContractError):
            InferenceReceipt.from_dict(coerced)

    def test_checkpoint_rejects_schema_and_field_drift_even_if_redigested(self):
        runtime = _runtime()
        bad_runtime = deepcopy(runtime.checkpoint())
        bad_runtime["runtime_schema"] = "skeleton.ai.native-llm-runtime.v999"
        bad_runtime = _redigest_checkpoint(bad_runtime)
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(bad_runtime)

        extra = deepcopy(runtime.checkpoint())
        extra["unexpected"] = True
        extra = _redigest_checkpoint(extra)
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(extra)

        coerced = deepcopy(runtime.checkpoint())
        coerced["limits"]["max_context_tokens"] = str(
            coerced["limits"]["max_context_tokens"]
        )
        coerced = _redigest_checkpoint(coerced)
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(coerced)

    def test_observability_records_digests_and_counts_not_raw_prompt(self):
        runtime = _runtime()
        secret_prompt = "hello world private-marker-7f62"
        runtime.generate(
            secret_prompt,
            SamplingConfig(
                max_new_tokens=2,
                seed=1,
                context_policy="truncate-left",
            ),
        )
        serialized = json.dumps(
            [event.to_dict() for event in runtime.events()],
            sort_keys=True,
        )
        self.assertNotIn("private-marker-7f62", serialized)
        metrics = runtime.metrics()
        self.assertEqual(metrics["requests"], 1)
        self.assertEqual(metrics["generated_tokens"], 2)


if __name__ == "__main__":
    unittest.main()
