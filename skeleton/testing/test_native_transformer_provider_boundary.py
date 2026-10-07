import asyncio
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import DevicePolicy, NativeLLMRuntime
from skeleton.ai.runtime.inference import LocalInferenceEngine, LocalModelAdapter, NativeTransformerModel
from skeleton.provider_runtime import ProviderRequest
from skeleton.providers.contract import FinishReason


class TestNativeTransformerProviderBoundary(unittest.TestCase):
    def adapter(self):
        runtime = NativeLLMRuntime(
            TinyTransformer(
                vocab=("system", "user", "assistant", "hello", "world", "native", "runtime", "text"),
                dim=16,
                ctx=32,
                seed=811,
                n_heads=4,
                n_layers=2,
                d_ff=32,
            ),
            device_policy=DevicePolicy("cpu"),
        )
        backend = NativeTransformerModel(runtime)
        return LocalModelAdapter(LocalInferenceEngine(backend, cache_size=4)), backend

    def test_provider_neutral_request_executes_native_transformer(self):
        async def scenario():
            adapter, backend = self.adapter()
            response = await adapter.generate(
                ProviderRequest(
                    instructions="answer locally",
                    prompt="hello world",
                    max_output_tokens=3,
                    operation_id="op-native-1",
                    execution_id="exec-native-1",
                    turn_id="turn-native-1",
                    context_id="ctx-native-1",
                    context_digest="a" * 64,
                    context_source_snapshot=(("source", "b" * 64),),
                    context_compiler_version="native-test-v1",
                )
            )
            self.assertEqual(response.provider, "local")
            self.assertEqual(response.model, backend.model_id)
            self.assertEqual(response.finish_reason, FinishReason.LENGTH)
            self.assertEqual(response.usage.output_tokens, 3)
            self.assertEqual(response.usage.total_tokens, response.usage.input_tokens + 3)
            self.assertEqual(response.usage.estimated_cost, "0")
            self.assertEqual(response.context_id, "ctx-native-1")
            self.assertEqual(response.context_digest, "a" * 64)
            self.assertEqual(adapter.runtime_digest, backend.runtime_digest)
            self.assertEqual(adapter.status()["model_digest"], backend.model_digest)
            self.assertEqual(adapter.status()["runtime_digest"], backend.runtime_digest)
        asyncio.run(scenario())

    def test_same_provider_request_is_deterministic(self):
        async def scenario():
            adapter, _ = self.adapter()
            request = ProviderRequest(
                instructions="answer locally",
                prompt="hello",
                max_output_tokens=4,
                operation_id="op-replay",
                execution_id="exec-replay",
                turn_id="turn-replay",
            )
            first = await adapter.generate(request)
            second = await adapter.generate(request)
            self.assertEqual(first.text, second.text)
            self.assertEqual(first.response_id, second.response_id)
            self.assertEqual(first.usage.output_tokens, second.usage.output_tokens)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
