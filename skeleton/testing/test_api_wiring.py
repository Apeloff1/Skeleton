"""Tests for cortex live singleton and API server state wiring."""

from __future__ import annotations

import unittest


class TestCortexLive(unittest.TestCase):
    def test_singleton(self):
        from skeleton.cortex import live
        c1 = live.get_live()
        c2 = live.get_live()
        self.assertIs(c1, c2)

    def test_attach_captures_events(self):
        from skeleton.cortex import live
        from skeleton.kernel.events import EventBus

        bus = EventBus()
        cortex = live.attach(bus)
        bus.emit("live.test", {"data": 1})
        events = cortex.recent_events("live.test", n=1)
        self.assertGreaterEqual(len(events), 1)

    def test_status(self):
        from skeleton.cortex import live
        live.get_live()
        status = live.status()
        self.assertTrue(status["live"])


class TestServerStateWiring(unittest.TestCase):
    def test_wire_from_genesis(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis

        state = ServerState()
        state.wire_from_genesis(Genesis(seed=42).boot())

        self.assertIsNotNone(state.genesis)
        self.assertIsNotNone(state.mesh)
        self.assertIsNotNone(state.memory_trinity)
        self.assertIsNotNone(state.resilience)
        self.assertIsNotNone(state.jeeves)
        self.assertIsNotNone(state.npc_pipeline)
        self.assertIsNotNone(state.game_logic_pipeline)
        self.assertIsNotNone(state.animation_pipeline)

    def test_jeeves_has_provider(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis

        state = ServerState()
        state.wire_from_genesis(Genesis(seed=42).boot())
        self.assertIn(state.jeeves.provider_name, ("local-echo", "openai", "anthropic"))

    def test_jeeves_ask_through_state(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis
        from skeleton.memory.core import Chunk

        state = ServerState()
        genesis = Genesis(seed=42).boot()
        genesis.get("rag").add(Chunk(text="skeleton forge builds blueprints", chunk_id="jeeves-1"))
        state.wire_from_genesis(genesis)

        session = state.jeeves.open_session("api-user")
        reply = state.jeeves.ask(session.session_id, "what does the forge build?")
        self.assertIn("content", reply)
        self.assertIn("forge", reply["content"].lower())

    def test_health_probes(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis

        state = ServerState()
        state.wire_from_genesis(Genesis(seed=42).boot())
        self.assertTrue(state.health.liveness()["alive"])
        self.assertTrue(state.health.readiness()["ready"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
