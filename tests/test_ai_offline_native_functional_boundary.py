"""Actual CPU-only native inference, replay and checkpoint acceptance subset.

A tiny deterministic untrained transformer is used solely to verify genuine
tokenization/attention/decoding/replay pathways without network, provider
credentials or GPU. It is NOT quality proof for a trained local GGUF model.
"""
from __future__ import annotations

from copy import deepcopy
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import (
    NativeLLMRuntime, NativeConversationSession)
from skeleton.ai.model_runtime.runtime_contracts import (
    DevicePolicy, GenerationConfig, ReplayMismatch, RuntimeContractError)


class NativeOfflineFunctionalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.model=TinyTransformer(
            vocab=("hello","world","original","game"),
            dim=8,ctx=12,seed=28,n_heads=2,n_layers=2,d_ff=12)
        self.runtime=NativeLLMRuntime(
            self.model,device_policy=DevicePolicy(requested="cpu"))
        self.config=GenerationConfig(
            max_new_tokens=3,seed=73,temperature=0.8,top_k=2)

    def test_real_cpu_tokenization_transformer_inference_and_replay(self):
        before=self.runtime.model_digest
        sequence=self.runtime.encode("hello world")
        self.assertTrue(sequence.token_ids)
        forward=self.runtime.infer_sequence(sequence)
        self.assertEqual(len(forward.logits),self.runtime.tokenizer.vocab_size)
        result=self.runtime.generate("hello world",self.config)
        self.assertLessEqual(len(result.generated_ids),3)
        self.assertEqual(len(result.generated_ids),len(result.generated_tokens))
        self.assertEqual(self.runtime.model_digest,before)
        replay=self.runtime.replay(result.replay_receipt,"hello world",self.config)
        self.assertEqual(replay.output_digest,result.output_digest)
        self.assertEqual(replay.generated_ids,result.generated_ids)

    def test_real_checkpoint_restore_reproduces_model_identity(self):
        saved=self.runtime.checkpoint_json()
        restored=NativeLLMRuntime.restore_json(saved)
        self.assertEqual(restored.model_digest,self.runtime.model_digest)
        self.assertEqual(restored.tokenizer.digest,self.runtime.tokenizer.digest)
        before=self.runtime.generate("hello",self.config)
        after=restored.generate("hello",self.config)
        self.assertEqual(before.generated_ids,after.generated_ids)
        self.assertEqual(before.output_digest,after.output_digest)

    def test_chat_session_retains_actual_tokens_with_bounded_context(self):
        session=NativeConversationSession(self.runtime)
        self.assertTrue(session.is_empty)
        receipt=session.generate("hello",self.config)
        self.assertEqual(session.turns,1)
        self.assertGreater(session.context_used,0)
        self.assertLessEqual(session.context_used,self.runtime.limits.max_context)
        self.assertEqual(session.context_used+session.context_remaining,
                         self.runtime.limits.max_context)
        self.assertEqual(receipt.replay_receipt.model_digest,
                         self.runtime.model_digest)

    def test_model_weight_mutation_invalidates_runtime_authority(self):
        original=self.runtime.model_digest
        self.model.E[0][0]+=0.75
        with self.assertRaises(RuntimeContractError):
            self.runtime.generate("hello",self.config)
        self.assertEqual(self.runtime.model_digest,original)

    def test_bad_context_budget_and_untrusted_device_deny_execution(self):
        with self.assertRaises(RuntimeContractError):
            self.runtime.generate("hello world "*30,self.config)
        with self.assertRaises(RuntimeContractError):
            self.runtime.generate(
                "hello",GenerationConfig(max_new_tokens=99999))
        with self.assertRaises(RuntimeContractError):
            DevicePolicy(requested="unsupported-accelerator")


if __name__ == "__main__":
    unittest.main()
