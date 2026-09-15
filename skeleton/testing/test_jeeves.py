"""Tests for Jeeves LLM provider abstraction and session hardening."""

from __future__ import annotations

import os
import unittest


class RecordingProvider:
    name = "recording"

    def __init__(self):
        self.last_prompt = None
        self.last_context = None

    def complete(self, prompt, context=None):
        self.last_prompt = prompt
        self.last_context = context
        return "recorded"


class FailingProvider:
    name = "failing"

    def complete(self, prompt, context=None):
        raise RuntimeError("provider-token=super-secret")


class TestLocalEchoProvider(unittest.TestCase):
    def test_always_available(self):
        from skeleton.jeeves.providers import LocalEchoProvider

        self.assertTrue(LocalEchoProvider().available())

    def test_uses_retriever_context(self):
        from skeleton.jeeves.providers import LocalEchoProvider
        from skeleton.memory.vector import VectorStore
        from skeleton.memory.core import Chunk

        store = VectorStore()
        store.add(Chunk(text="the forge builds blueprints from components", chunk_id="x1"))

        class FakeQuad:
            def retrieve(self, q, k=3):
                return store.query(q, top_k=k)

        provider = LocalEchoProvider(retriever=FakeQuad())
        out = provider.complete("what does the forge build?")
        self.assertIn("forge", out.lower())

    def test_no_context_fallback(self):
        from skeleton.jeeves.providers import LocalEchoProvider

        out = LocalEchoProvider().complete("anything at all")
        self.assertIn("context", out.lower())


class TestProviderFactory(unittest.TestCase):
    def test_defaults_to_local_without_keys(self):
        from skeleton.jeeves.providers import get_provider

        os.environ.pop("SKELETON_OPENAI_API_KEY", None)
        os.environ.pop("SKELETON_ANTHROPIC_API_KEY", None)
        os.environ.pop("SKELETON_LLM_PROVIDER", None)
        provider = get_provider()
        self.assertEqual(provider.name, "local-echo")

    def test_explicit_local_choice(self):
        from skeleton.jeeves.providers import get_provider

        provider = get_provider(preferred="local")
        self.assertEqual(provider.name, "local-echo")

    def test_openai_unavailable_without_key(self):
        from skeleton.jeeves.providers import OpenAIProvider

        os.environ.pop("SKELETON_OPENAI_API_KEY", None)
        self.assertFalse(OpenAIProvider().available())


class TestJeevesWithProvider(unittest.TestCase):
    def test_ask_uses_provider(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.core import SessionMode as LegacySessionMode
        from skeleton.jeeves.providers import LocalEchoProvider

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("user-1", mode=LegacySessionMode.ANALYTICAL)
        reply = jeeves.ask(session.session_id, "analyze this")
        self.assertEqual(reply["provider"], "local-echo")
        self.assertEqual(reply["mode"], "analytical")
        self.assertIn("content", reply)
        self.assertEqual(jeeves.provider_name, "local-echo")

    def test_session_records_provider(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("user-2")
        jeeves.ask(session.session_id, "hello")
        last = session.turns[-1]
        self.assertEqual(last.metadata.get("provider"), "local-echo")
        self.assertTrue(last.metadata.get("success"))

    def test_legacy_mode_is_normalized_and_prompted(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.core import SessionMode as LegacySessionMode
        from skeleton.jeeves.llm_core import SessionMode

        provider = RecordingProvider()
        jeeves = JeevesCore(provider=provider)
        session = jeeves.open_session("api-user", mode=LegacySessionMode.ANALYTICAL)
        reply = jeeves.ask(session.session_id, "compare the designs")

        self.assertIs(session.mode, SessionMode.ANALYTICAL)
        self.assertEqual(reply["mode"], "analytical")
        self.assertIn("precise analyst", provider.last_prompt)

    def test_extended_public_modes_are_supported(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.core import SessionMode as LegacySessionMode
        from skeleton.jeeves.llm_core import SessionMode

        provider = RecordingProvider()
        jeeves = JeevesCore(provider=provider)
        for legacy_mode in (
            LegacySessionMode.CO_CODING,
            LegacySessionMode.TACTICAL,
            LegacySessionMode.BUILDER,
            LegacySessionMode.CORTEX,
        ):
            session = jeeves.open_session("api-user", mode=legacy_mode)
            self.assertEqual(session.mode, SessionMode(legacy_mode.value))
            reply = jeeves.ask(session.session_id, "next step")
            self.assertEqual(reply["mode"], legacy_mode.value)
            self.assertTrue(provider.last_prompt.startswith("You are"))

    def test_provider_exception_details_are_redacted(self):
        from skeleton.jeeves import JeevesCore

        jeeves = JeevesCore(provider=FailingProvider())
        session = jeeves.open_session("user-3")
        reply = jeeves.ask(session.session_id, "hello")

        self.assertEqual(reply["content"], "[provider unavailable]")
        self.assertEqual(reply["provider_error"], "RuntimeError")
        self.assertNotIn("super-secret", str(reply))
        self.assertNotIn("super-secret", session.turns[-1].content)
        self.assertFalse(session.turns[-1].metadata.get("success"))

    def test_empty_and_oversized_inputs_are_rejected_without_turns(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.llm_core import MAX_INPUT_CHARS

        jeeves = JeevesCore(provider=RecordingProvider())
        session = jeeves.open_session("user-4")

        empty = jeeves.ask(session.session_id, "   ")
        oversized = jeeves.ask(session.session_id, "x" * (MAX_INPUT_CHARS + 1))

        self.assertEqual(empty["error"], "Input must be non-empty")
        self.assertEqual(oversized["error"], "Input too large")
        self.assertEqual(oversized["max_input_chars"], MAX_INPUT_CHARS)
        self.assertEqual(session.turns, [])


class TestMemoryManager(unittest.TestCase):
    def test_eviction_removes_stale_user_index(self):
        from skeleton.jeeves.llm_core import MemoryManager

        memory = MemoryManager(max_sessions=1)
        first = memory.create_session("first-user")
        second = memory.create_session("second-user")

        self.assertIsNone(memory.get_session(first.session_id))
        self.assertEqual(memory.get_user_history("first-user"), [])
        self.assertEqual(memory.get_user_history("second-user"), [second])
        self.assertEqual(memory.stats()["users"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
