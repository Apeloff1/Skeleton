import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.local_model_bridge import (
    CancellationToken,
    GenerationConfig,
    LocalModelReceipt,
    LocalModelRequest,
    ModelRuntimeError,
    NativeLLMRuntime,
    NativeModelService,
)

D = "a" * 64


class TestLocalBridge(unittest.TestCase):
    def test_bridge_is_inference_only_and_failed_output_is_fenced(self):
        req = LocalModelRequest("op", D, D, 32, 1000)
        self.assertEqual(req.authority_scope, "inference-only")
        with self.assertRaises(ModelRuntimeError):
            LocalModelRequest("op", D, D, 32, 1000, "execute")
        with self.assertRaises(ModelRuntimeError):
            LocalModelReceipt("op", D, "cancelled", D, D)

    def test_bridge_module_exposes_governed_native_service(self):
        runtime = NativeLLMRuntime(
            TinyTransformer(
                vocab=("hello", "world"),
                dim=8,
                ctx=6,
                seed=13,
                n_heads=2,
                n_layers=2,
                d_ff=12,
            )
        )
        service = NativeModelService(runtime)
        config = GenerationConfig(max_new_tokens=2, seed=1, temperature=0.0)
        request = service.request("op-native", "hello", config, deadline_ms=1000)
        result = service.execute(request, "hello", config)
        self.assertEqual(result.receipt.terminal_reason, "completed")
        self.assertEqual(result.receipt.model_identity_digest, runtime.model_identity.identity_digest)
        self.assertIsNotNone(result.generation)

    def test_cancellation_type_is_exported_at_bridge_boundary(self):
        token = CancellationToken()
        self.assertFalse(token.cancelled)
        token.cancel()
        self.assertTrue(token.cancelled)


if __name__ == "__main__":
    unittest.main()
