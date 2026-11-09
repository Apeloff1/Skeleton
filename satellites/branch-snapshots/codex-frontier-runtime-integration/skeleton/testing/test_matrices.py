"""Tests for Jeeves memory matrices (SAM, CLOM, KREM) and their wiring."""

from __future__ import annotations

import time
import unittest


class TestSAM(unittest.TestCase):
    def setUp(self):
        from skeleton.jeeves.matrices import SemanticAssociationMap
        self.sam = SemanticAssociationMap()

    def test_cooccurrence_builds_edges(self):
        self.sam.observe("the forge builds blueprints for games")
        self.sam.observe("forge blueprints target godot engine")
        assocs = dict(self.sam.associations("forge"))
        self.assertIn("blueprints", assocs)

    def test_expand_returns_associated_terms(self):
        self.sam.observe("skeleton forge builds game blueprints")
        self.sam.observe("skeleton forge materialises game worlds")
        expansions = self.sam.expand("skeleton")
        self.assertTrue(any(t in expansions for t in ("forge", "game", "builds")))

    def test_decay_prunes_weak_edges(self):
        self.sam.observe("alpha beta gamma delta")
        for _ in range(200):
            self.sam.decay()
        self.assertEqual(self.sam.snapshot()["edges"], 0)

    def test_snapshot_shape(self):
        self.sam.observe("one two three four five")
        snap = self.sam.snapshot()
        self.assertIn("terms", snap)
        self.assertIn("edges", snap)
        self.assertIn("strongest", snap)


class TestCLOM(unittest.TestCase):
    def setUp(self):
        from skeleton.jeeves.matrices import CompressedLearnedOutcomeModel
        self.clom = CompressedLearnedOutcomeModel()

    def test_success_rate(self):
        for _ in range(8):
            self.clom.observe("tutoring", True, 50.0)
        for _ in range(2):
            self.clom.observe("tutoring", False, 80.0)
        self.assertAlmostEqual(self.clom.success_rate("tutoring"), 0.8)

    def test_degraded_detection(self):
        for _ in range(6):
            self.clom.observe("debug", False, 100.0)
        self.assertIn("debug", self.clom.degraded())

    def test_best_intent(self):
        for _ in range(5):
            self.clom.observe("creative", True, 30.0)
        for _ in range(5):
            self.clom.observe("analytical", False, 30.0)
        self.assertEqual(self.clom.best_intent(), "creative")

    def test_window_trims(self):
        clom = type(self.clom)(window=10)
        for i in range(20):
            clom.observe("x", True, 1.0)
        self.assertEqual(len(clom._records["x"]), 10)


class TestKREM(unittest.TestCase):
    def setUp(self):
        from skeleton.jeeves.matrices import KnowledgeRetentionMatrix
        self.krem = KnowledgeRetentionMatrix()

    def test_observe_creates_cell_at_full_strength(self):
        self.krem.observe("forge")
        self.assertAlmostEqual(self.krem.retention("forge"), 1.0, places=2)

    def test_unknown_concept_zero(self):
        self.assertEqual(self.krem.retention("nonexistent"), 0.0)

    def test_due_after_decay(self):
        self.krem.observe("stale-concept")
        cell = self.krem._cells["stale-concept"]
        # Simulate 10 half-lives elapsed
        cell.last_seen = time.time() - (self.krem.HALF_LIFE_HOURS * 10 * 3600)
        self.assertIn("stale-concept", self.krem.due())

    def test_review_strengthens(self):
        self.krem.observe("forge")
        self.krem.observe("forge")
        cell = self.krem._cells["forge"]
        self.assertEqual(cell.reviews, 1)
        self.assertGreater(cell.strength, 1.0)


class TestMatricesInJeeves(unittest.TestCase):
    def test_ask_observes_matrices(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("matrix-user")
        jeeves.ask(session.session_id, "tell me about forge blueprints")

        self.assertGreater(jeeves.sam.stats()["terms"], 0)
        self.assertGreater(jeeves.clom.stats()["records"], 0)
        self.assertGreater(jeeves.krem.stats()["concepts"], 0)

    def test_matrices_snapshot_shape(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("snap-user")
        jeeves.ask(session.session_id, "hello skeleton world")

        m = jeeves.matrices()
        self.assertIn("sam", m)
        self.assertIn("clom", m)
        self.assertIn("krem", m)

    def test_clom_records_mode_outcome(self):
        from skeleton.jeeves import JeevesCore, SessionMode
        from skeleton.jeeves.providers import LocalEchoProvider

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("mode-user", mode=SessionMode.ANALYTICAL)
        jeeves.ask(session.session_id, "analyze this")
        self.assertEqual(jeeves.clom.success_rate("analytical"), 1.0)

    def test_server_state_exposes_matrices(self):
        from skeleton.api.server import ServerState
        from skeleton.genesis import Genesis

        state = ServerState()
        state.wire_from_genesis(Genesis(seed=42).boot())
        self.assertIsNotNone(state.jeeves_sam)
        self.assertIsNotNone(state.jeeves_clom)
        self.assertIsNotNone(state.jeeves_krem)

        session = state.jeeves.open_session("state-user")
        state.jeeves.ask(session.session_id, "forge builds blueprints")
        self.assertGreater(state.jeeves_sam.stats()["terms"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
