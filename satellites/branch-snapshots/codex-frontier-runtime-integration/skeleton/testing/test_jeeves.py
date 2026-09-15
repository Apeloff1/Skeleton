"""Tests for Jeeves LLM provider abstraction."""

from __future__ import annotations

import os
import unittest


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
        from skeleton.jeeves.core import JeevesCore, SessionMode
        from skeleton.jeeves.providers import LocalEchoProvider

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("user-1", mode=SessionMode.ANALYTICAL)
        reply = jeeves.ask(session.session_id, "analyze this")
        self.assertEqual(reply["provider"], "local-echo")
        self.assertIn("content", reply)
        self.assertEqual(jeeves.provider_name, "local-echo")

    def test_session_records_provider(self):
        from skeleton.jeeves.core import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("user-2")
        jeeves.ask(session.session_id, "hello")
        last = session.turns[-1]
        self.assertEqual(last.metadata.get("provider"), "local-echo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
