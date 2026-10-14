"""Native serving admission must not partially mutate identity or device policy."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import DevicePolicy, NativeLLMRuntime, RuntimeContractError
from skeleton.ai.model_runtime.tokenization import TokenizerContractError


class TestNativeAtomicIdentity(unittest.TestCase):
    def runtime(self):
        return NativeLLMRuntime(
            TinyTransformer(
                vocab=("hello", "world", "runtime", "token"),
                dim=8, ctx=8, seed=17, n_heads=2, n_layers=2, d_ff=16,
            ),
            device_policy=DevicePolicy("cpu"),
        )

    def test_model_context_shrink_does_not_mutate_admitted_identity(self):
        runtime = self.runtime()
        identity = (runtime.model_digest, runtime.architecture, runtime.tokenizer, runtime.model_bytes)
        runtime.model.ctx = 4
        with self.assertRaises(RuntimeContractError):
            runtime.refresh_model_identity()
        self.assertEqual(runtime.model_digest, identity[0])
        self.assertIs(runtime.architecture, identity[1])
        self.assertIs(runtime.tokenizer, identity[2])
        self.assertEqual(runtime.model_bytes, identity[3])

    def test_tokenizer_readmission_failure_preserves_identity(self):
        runtime = self.runtime()
        original = (runtime.model_digest, runtime.architecture, runtime.tokenizer)
        with patch("skeleton.ai.model_runtime.native_llm_runtime.NativeTokenizer",
                   side_effect=TokenizerContractError("tokenizer rejected")):
            with self.assertRaisesRegex(RuntimeContractError, "tokenizer re-admission"):
                runtime.refresh_model_identity()
        self.assertEqual(runtime.model_digest, original[0])
        self.assertIs(runtime.architecture, original[1])
        self.assertIs(runtime.tokenizer, original[2])

    def test_failed_device_rebind_preserves_original_policy(self):
        runtime = self.runtime()
        before_policy, before_receipt = runtime.device_policy, runtime.device
        with patch.object(runtime, "_bind_device", side_effect=RuntimeContractError("device unavailable")):
            with self.assertRaisesRegex(RuntimeContractError, "device unavailable"):
                runtime.bind_device(DevicePolicy("cpu"))
        self.assertIs(runtime.device_policy, before_policy)
        self.assertIs(runtime.device, before_receipt)

    def test_successful_weight_readmission_commits_new_digest(self):
        runtime = self.runtime()
        prior = runtime.model_digest
        runtime.model.bout[0] += 0.125
        self.assertNotEqual(runtime.refresh_model_identity(), prior)
        self.assertEqual(runtime.model_digest, runtime.health_snapshot()["model_digest"])
        runtime.assert_model_unchanged()


if __name__ == "__main__":
    unittest.main()
