"""Targeted native LLM serving regressions."""
import copy
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, ReplayMismatch, RuntimeContractError


def _model():
    return TinyTransformer({"alpha", "beta", "gamma", "delta"}, dim=8, ctx=6, seed=17, n_heads=2, n_layers=2, d_ff=12)


class NativeRuntimeRegressionTests(unittest.TestCase):
    def test_new_token_ownership_and_cache_parity(self):
        runtime = NativeLLMRuntime(_model())
        prompt = runtime.encode("alpha beta")
        base = dict(max_new_tokens=4, seed=91, temperature=0.7, top_k=3, top_p=0.9)
        cached = runtime.generate("alpha beta", GenerationConfig(**base, use_cache=True))
        plain = runtime.generate("alpha beta", GenerationConfig(**base, use_cache=False))
        self.assertEqual(len(cached.generated_ids), 4)
        self.assertEqual(cached.usage.prompt_tokens, len(prompt.token_ids))
        self.assertEqual(cached.generated_ids, plain.generated_ids)
        self.assertEqual(cached.output_digest, plain.output_digest)

    def test_replay_checkpoint_and_tamper_detection(self):
        runtime = NativeLLMRuntime(_model())
        config = GenerationConfig(max_new_tokens=3, seed=7, temperature=0.0)
        first = runtime.generate("alpha beta", config)
        replayed = runtime.replay(first.replay_receipt, "alpha beta", config)
        self.assertEqual(first.output_digest, replayed.output_digest)
        with self.assertRaises(ReplayMismatch):
            runtime.replay(first.replay_receipt, "alpha gamma", config)
        restored = NativeLLMRuntime.restore_json(runtime.checkpoint_json())
        self.assertEqual(first.generated_ids, restored.generate("alpha beta", config).generated_ids)
        tampered = copy.deepcopy(runtime.checkpoint())
        tampered["model"]["bout"][0] += 1.0
        with self.assertRaises(RuntimeContractError):
            NativeLLMRuntime.restore(tampered)

    def test_weight_mutation_requires_readmission(self):
        runtime = NativeLLMRuntime(_model())
        old = runtime.model_digest
        runtime.model.bout[0] += 0.25
        with self.assertRaises(RuntimeContractError):
            runtime.generate("alpha", GenerationConfig(max_new_tokens=1))
        self.assertNotEqual(old, runtime.refresh_model_identity())
        runtime.generate("alpha", GenerationConfig(max_new_tokens=1))


    def test_interleaved_native_batch_preserves_independent_replay(self):
        from dataclasses import replace
        from skeleton.ai.model_runtime.runtime_contracts import BatchGenerationRequest, RuntimeLimits
        model = _model()
        runtime = NativeLLMRuntime(model, limits=replace(RuntimeLimits.for_model(model), max_kv_bytes=16384))
        config = GenerationConfig(max_new_tokens=3, seed=11, temperature=0.7)
        requests = (
            BatchGenerationRequest("first", "alpha beta", config),
            BatchGenerationRequest("second", "gamma delta", config),
            BatchGenerationRequest("third", "beta gamma", config),
        )
        serial = runtime.generate_batch(requests)
        observed = []
        interleaved = runtime.generate_interleaved_batch(
            requests, max_active_slots=2, max_resident_kv_bytes=32768,
            on_event=lambda name, event: observed.append(name),
        )
        self.assertEqual([row.request_id for row in interleaved], [row.request_id for row in serial])
        self.assertEqual([row.result.generated_ids for row in interleaved],
                         [row.result.generated_ids for row in serial])
        self.assertEqual([row.result.output_digest for row in interleaved],
                         [row.result.output_digest for row in serial])
        self.assertEqual(observed[:4], ["first", "second", "first", "second"])

    def test_interleaved_budget_rejects_before_stream_dispatch(self):
        from dataclasses import replace
        from skeleton.ai.model_runtime.runtime_contracts import BatchGenerationRequest, RuntimeLimits
        model = _model()
        runtime = NativeLLMRuntime(model, limits=replace(RuntimeLimits.for_model(model), max_kv_bytes=16384))
        requests = (BatchGenerationRequest("first", "alpha", GenerationConfig(max_new_tokens=1)),)
        events = []
        with self.assertRaisesRegex(RuntimeContractError, "aggregate KV"):
            runtime.generate_interleaved_batch(requests, max_active_slots=1,
                max_resident_kv_bytes=8192, on_event=lambda *args: events.append(args))
        self.assertEqual(events, [])

    def test_interleaved_observer_failure_drains_pending_streams(self):
        from dataclasses import replace
        from skeleton.ai.model_runtime.runtime_contracts import BatchGenerationRequest, RuntimeLimits
        model = _model()
        runtime = NativeLLMRuntime(model, limits=replace(RuntimeLimits.for_model(model), max_kv_bytes=16384))
        requests = (BatchGenerationRequest("first", "alpha", GenerationConfig(max_new_tokens=1)),
                    BatchGenerationRequest("second", "beta", GenerationConfig(max_new_tokens=1)))
        def reject(name, event):
            if name == "second":
                raise RuntimeError("observer stopped")
        with self.assertRaisesRegex(RuntimeError, "observer stopped"):
            runtime.generate_interleaved_batch(requests, max_active_slots=2,
                max_resident_kv_bytes=32768, on_event=reject)
        self.assertEqual(len(runtime.generate_batch(requests)), 2)


if __name__ == "__main__":
    unittest.main()
