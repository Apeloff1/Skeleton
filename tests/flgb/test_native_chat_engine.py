"""Executable role-chat adapter integration tests."""
import unittest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime import (
    ChatMessage, ChatTranscript, DevicePolicy, GenerationConfig,
    NativeChatEngine, NativeLLMRuntime, RuntimeContractError,
)


class NativeChatEngineTests(unittest.TestCase):
    def setUp(self):
        self.runtime = NativeLLMRuntime(TinyTransformer(
            vocab=("hello", "world", "again", "small", "runtime", "token"),
            dim=8, ctx=256, seed=11, n_heads=2, n_layers=2, d_ff=16),
            device_policy=DevicePolicy("cpu"))
        self.engine = NativeChatEngine(self.runtime)
        self.config = GenerationConfig(max_new_tokens=2, temperature=0.0)

    def test_preflight_accounts_for_completion_budget(self):
        transcript = ChatTranscript((ChatMessage("user", "hello"),))
        plan = self.engine.preflight(transcript, self.config)
        self.assertGreater(plan["prompt_tokens"], 0)
        self.assertGreaterEqual(plan["remaining_context"], 2)

    def test_generate_commits_assistant_reply(self):
        transcript = ChatTranscript((ChatMessage("user", "hello world"),))
        result = self.engine.generate(transcript, self.config)
        self.assertEqual(result.transcript.last_role(), "assistant")
        self.assertEqual(result.transcript.last_assistant_message().content,
                         result.generation.text)
        self.assertEqual(len(result.generation.generated_ids), 2)

    def test_turn_does_not_mutate_original(self):
        original = ChatTranscript(())
        result = self.engine.turn(original, "hello", self.config)
        self.assertEqual(original.messages, ())
        self.assertEqual(result.transcript.messages[0].role, "user")

    def test_reject_assistant_only_prompt(self):
        transcript = ChatTranscript((ChatMessage("assistant", "hello"),))
        with self.assertRaises(RuntimeContractError):
            self.engine.generate(transcript, self.config)

    def test_latest_user_message_not_discarded(self):
        oversized = ChatTranscript((ChatMessage("user", "hello " * 300),))
        with self.assertRaises(RuntimeContractError):
            self.engine.fit(oversized, self.config)

    def test_reject_impossible_reserve(self):
        with self.assertRaises(RuntimeContractError):
            NativeChatEngine(self.runtime, reserve_tokens=256)


if __name__ == "__main__":
    unittest.main()
