import unittest
from hashlib import sha256

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.local_model_bridge import (
    GenerationConfig,
    LocalModelReceipt,
    LocalModelRequest,
    ModelRuntimeError,
    NativeLLMRuntime,
    RuntimeContractError,
    execute_local_request,
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

    def test_native_runtime_executes_bridge_request_with_receipts(self):
        model = TinyTransformer(
            vocab=("hello", "world", "runtime"),
            dim=8,
            ctx=8,
            seed=23,
            n_heads=2,
            n_layers=2,
            d_ff=16,
        )
        runtime = NativeLLMRuntime(model)
        prompt = "hello world"
        request = LocalModelRequest(
            "op-native",
            runtime.model_identity.identity_digest,
            sha256(prompt.encode("utf-8")).hexdigest(),
            3,
            1000,
        )
        result, receipt = execute_local_request(
            runtime,
            request,
            prompt,
            GenerationConfig(max_new_tokens=2, seed=5, temperature=0.0),
        )
        self.assertEqual(receipt.operation_id, request.operation_id)
        self.assertEqual(receipt.model_identity_digest, request.model_identity_digest)
        self.assertEqual(receipt.terminal_reason, "completed")
        self.assertEqual(receipt.output_digest, result.output_digest)
        self.assertEqual(receipt.usage_digest, result.usage.digest)

    def test_native_bridge_rejects_identity_input_and_output_budget_drift(self):
        runtime = NativeLLMRuntime(
            TinyTransformer(
                vocab=("alpha", "beta"),
                dim=8,
                ctx=6,
                seed=29,
                n_heads=2,
                n_layers=2,
                d_ff=12,
            )
        )
        prompt = "alpha beta"
        prompt_digest = sha256(prompt.encode("utf-8")).hexdigest()
        identity = runtime.model_identity.identity_digest

        with self.assertRaises(RuntimeContractError):
            execute_local_request(
                runtime,
                LocalModelRequest("bad-model", D, prompt_digest, 2, 1000),
                prompt,
            )
        with self.assertRaises(RuntimeContractError):
            execute_local_request(
                runtime,
                LocalModelRequest("bad-input", identity, D, 2, 1000),
                prompt,
            )
        with self.assertRaises(RuntimeContractError):
            execute_local_request(
                runtime,
                LocalModelRequest("bad-budget", identity, prompt_digest, 1, 1000),
                prompt,
                GenerationConfig(max_new_tokens=2),
            )


if __name__ == "__main__":
    unittest.main()
