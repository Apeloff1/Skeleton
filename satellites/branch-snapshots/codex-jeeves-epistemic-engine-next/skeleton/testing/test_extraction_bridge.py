"""Tests for triple extraction, quad self-population, and the swarm bridge."""

from __future__ import annotations

import unittest


class TestTripleExtractor(unittest.TestCase):
    def setUp(self):
        from skeleton.retrieval.extraction import TripleExtractor
        self.extractor = TripleExtractor()

    def test_is_a_extraction(self):
        triples = self.extractor.extract("Skeleton is a game engine.")
        self.assertIn(("Skeleton", "is_a", "game engine"), triples)

    def test_produces_extraction(self):
        triples = self.extractor.extract("The Forge produces blueprints for games.")
        subjects = [t[0] for t in triples]
        self.assertTrue(any("Forge" in s for s in subjects))

    def test_uses_extraction(self):
        triples = self.extractor.extract("Jeeves uses memory planes for context.")
        predicates = [t[1] for t in triples]
        self.assertIn("uses", predicates)

    def test_can_capability(self):
        triples = self.extractor.extract("The swarm can route tasks across agents.")
        self.assertTrue(any(t[1] == "can" for t in triples))

    def test_skips_stop_subjects(self):
        triples = self.extractor.extract("The system is a framework.")
        self.assertEqual([t for t in triples if t[0].lower() == "the system"], [])

    def test_stats_tracked(self):
        self.extractor.extract("Alpha is a beta. Gamma produces delta.")
        stats = self.extractor.stats()
        self.assertGreater(stats["sentences"], 0)
        self.assertGreater(stats["extracted"], 0)


class TestQuadSelfPopulation(unittest.TestCase):
    def test_ingest_populates_kag(self):
        from skeleton.genesis import Genesis

        g = Genesis(seed=42).boot()
        quad = g.get("quad")
        kag = quad._planes["kag"]
        self.assertEqual(kag.graph.stats()["triples"], 0)

        quad.ingest_document("doc-1", "Skeleton is a game engine. The Forge produces blueprints.")
        self.assertGreater(kag.graph.stats()["triples"], 0)

    def test_kag_answers_after_ingest(self):
        from skeleton.genesis import Genesis

        g = Genesis(seed=42).boot()
        quad = g.get("quad")
        quad.ingest_document("doc-2", "The Forge produces blueprints for games.")

        results = quad.retrieve("what does the Forge produce?", k=5)
        planes = {r.plane for r in results}
        self.assertIn("kag", planes)

    def test_cache_invalidated_on_ingest(self):
        from skeleton.genesis import Genesis

        g = Genesis(seed=42).boot()
        quad = g.get("quad")
        quad.retrieve("anything", k=3)
        self.assertGreater(quad.stats()["cache_size"], 0)
        quad.ingest_document("doc-3", "Skeleton is a platform.")
        self.assertEqual(quad.stats()["cache_size"], 0)

    def test_stats_track_triples(self):
        from skeleton.genesis import Genesis

        g = Genesis(seed=42).boot()
        quad = g.get("quad")
        quad.ingest_document("doc-4", "Alpha is a beta. Gamma uses delta.")
        self.assertGreater(quad.stats()["triples_extracted"], 0)


class TestSwarmBridge(unittest.TestCase):
    def test_genesis_wires_coordinator_and_bridge(self):
        from skeleton.genesis import Genesis

        g = Genesis(seed=42).boot()
        self.assertIn("coordinator", g.handles)
        self.assertIn("bridge", g.handles)

    def test_bridge_dispatches_onto_mesh(self):
        from skeleton.genesis import Genesis
        from skeleton.agents import Task, TaskStatus

        g = Genesis(seed=42).boot()
        mesh = g.get("mesh")
        bridge = g.get("bridge")
        mesh.join({"reasoning"}, weight=2.0)

        import uuid
        task = Task(task_id=str(uuid.uuid4())[:8], description="route me")
        ok = bridge.dispatch(task, "reasoning")
        self.assertTrue(ok)
        self.assertIn("mesh_agent_id", task.metadata)
        self.assertIsNotNone(bridge.assignment_for(task.task_id))

    def test_bridge_fails_without_capable_agent(self):
        from skeleton.genesis import Genesis
        from skeleton.agents import Task
        import uuid

        g = Genesis(seed=42).boot()
        bridge = g.get("bridge")
        task = Task(task_id=str(uuid.uuid4())[:8], description="nowhere to go")
        self.assertFalse(bridge.dispatch(task, "teleportation"))
        self.assertEqual(bridge.stats()["failed"], 1)

    def test_release_clears_assignment(self):
        from skeleton.genesis import Genesis
        from skeleton.agents import Task
        import uuid

        g = Genesis(seed=42).boot()
        mesh = g.get("mesh")
        bridge = g.get("bridge")
        mesh.join({"compute"})
        task = Task(task_id=str(uuid.uuid4())[:8], description="compute job")
        bridge.dispatch(task, "compute")
        bridge.release(task.task_id)
        self.assertIsNone(bridge.assignment_for(task.task_id))


if __name__ == "__main__":
    unittest.main(verbosity=2)
