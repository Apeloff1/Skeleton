import asyncio
import threading
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import DevicePolicy, NativeLLMRuntime, RuntimeContractError
from skeleton.ai.runtime.inference import (
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    NativeTransformerModel,
)


class TestNativeTransformerLocalBackend(unittest.TestCase):
    def backend(self):
        model = TinyTransformer(
            vocab=("system", "user", "assistant", "hello", "world", "local", "model", "text"),
            dim=16,
            ctx=32,
            seed=77,
            n_heads=4,
            n_layers=2,
            d_ff=32,
        )
        runtime = NativeLLMRuntime(model, device_policy=DevicePolicy("cpu"))
        return NativeTransformerModel(runtime)

    def test_backend_satisfies_local_inference_contract(self):
        backend = self.backend()
        request = LocalInferenceRequest(prompt="hello world", max_output_tokens=3, seed=9)
        result = backend.infer(request, threading.Event())
        self.assertEqual(result.model_id, "skeleton-native-transformer")
        self.assertEqual(result.model_digest, backend.model_digest)
        self.assertEqual(result.output_tokens, 3)
        self.assertGreater(result.input_tokens, 0)
        self.assertIsNotNone(result.text)
        self.assertTrue(result.response_id.startswith("local-native:"))

    def test_engine_executes_native_transformer_and_caches_by_identity(self):
        async def scenario():
            engine = LocalInferenceEngine(self.backend(), cache_size=2)
            request = LocalInferenceRequest(prompt="hello", max_output_tokens=2, seed=4)
            first = await engine.generate(request)
            second = await engine.generate(request)
            self.assertFalse(first.cached)
            self.assertTrue(second.cached)
            self.assertEqual(first.text, second.text)
            self.assertEqual(first.model_digest, second.model_digest)
        asyncio.run(scenario())

    def test_precancelled_request_fails_without_decode(self):
        backend = self.backend()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(LocalInferenceCancelled):
            backend.infer(LocalInferenceRequest(prompt="hello"), cancel)

    def test_unsupported_capability_claims_fail_closed(self):
        backend = self.backend()
        with self.assertRaises(ValueError):
            backend.infer(
                LocalInferenceRequest(
                    prompt="hello",
                    tools=({"tool_id": "write", "input_schema": {"type": "object"}},),
                ),
                threading.Event(),
            )
        with self.assertRaises(ValueError):
            backend.infer(
                LocalInferenceRequest(
                    prompt="hello",
                    structured_output_schema={"type": "object"},
                ),
                threading.Event(),
            )

    def test_model_mutation_is_rejected_after_backend_binding(self):
        backend = self.backend()
        backend.runtime.model.bout[0] += 0.5
        with self.assertRaises(RuntimeContractError):
            backend.infer(LocalInferenceRequest(prompt="hello"), threading.Event())

    def test_runtime_identity_is_stable_and_sha256(self):
        backend = self.backend()
        self.assertEqual(len(backend.runtime_digest), 64)
        self.assertTrue(all(ch in "0123456789abcdef" for ch in backend.runtime_digest))
        self.assertEqual(backend.runtime_digest, backend._compute_runtime_digest())

    def test_tokenizer_mutation_is_rejected_after_backend_binding(self):
        backend = self.backend()
        backend.runtime.model.itos[0] = "mutated-token"
        with self.assertRaises(Exception):
            backend.infer(LocalInferenceRequest(prompt="hello"), threading.Event())

    def test_model_id_is_normalized_once_at_binding(self):
        backend = NativeTransformerModel(self.backend().runtime, model_id="  owned-native  ")
        self.assertEqual(backend.model_id, "owned-native")


if __name__ == "__main__":
    unittest.main()
