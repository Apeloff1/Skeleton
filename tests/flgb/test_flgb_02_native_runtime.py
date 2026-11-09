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


if __name__ == "__main__":
    unittest.main()
