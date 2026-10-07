"""Tests for the persistence layer."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path


class TestSnapshotStore(unittest.TestCase):
    def setUp(self):
        from skeleton.persistence import SnapshotStore
        self.tmp = Path(tempfile.mkdtemp())
        self.store = SnapshotStore(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load(self):
        self.store.save("test", {"key": "value", "n": 42})
        data = self.store.load("test")
        self.assertEqual(data["key"], "value")
        self.assertEqual(data["n"], 42)

    def test_load_missing_returns_none(self):
        self.assertIsNone(self.store.load("nonexistent"))

    def test_list_snapshots(self):
        self.store.save("a", {"x": 1})
        self.store.save("b", {"y": 2})
        names = {s["name"] for s in self.store.list()}
        self.assertEqual(names, {"a", "b"})

    def test_delete(self):
        self.store.save("d", {"z": 3})
        self.assertTrue(self.store.delete("d"))
        self.assertIsNone(self.store.load("d"))


class TestPlaneSerializers(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_vector_store_roundtrip(self):
        from skeleton.memory.vector import VectorStore
        from skeleton.memory.core import Chunk
        from skeleton.persistence import restore_vector_store, serialize_vector_store

        store = VectorStore()
        store.add(Chunk(text="skeleton forge builds blueprints", chunk_id="v1"))
        store.add(Chunk(text="swarm routes tasks by capability", chunk_id="v2"))

        data = serialize_vector_store(store)
        fresh = VectorStore()
        restored = restore_vector_store(data, fresh)

        self.assertEqual(restored, 2)
        results = fresh.query("forge blueprints")
        self.assertEqual(results[0].chunk.chunk_id, "v1")

    def test_mag_roundtrip(self):
        from skeleton.memory.core import MAGStore
        from skeleton.persistence import restore_mag, serialize_mag

        mag = MAGStore("agent-x")
        mag.record("e1", "fought the boss", tags=["combat", "boss"])

        data = serialize_mag(mag)
        fresh = MAGStore("agent-x")
        restored = restore_mag(data, fresh)

        self.assertEqual(restored, 1)
        self.assertEqual(fresh.recall_by_tag("boss")[0]["content"], "fought the boss")

    def test_graph_roundtrip(self):
        from skeleton.retrieval.kag import KnowledgeGraph
        from skeleton.persistence import restore_graph, serialize_graph

        graph = KnowledgeGraph()
        graph.add("forge", "produces", "blueprints")
        graph.add("blueprints", "target", "godot")

        data = serialize_graph(graph)
        fresh = KnowledgeGraph()
        restored = restore_graph(data, fresh)

        self.assertEqual(restored, 2)
        self.assertGreater(len(fresh.paths("forge", "godot")), 0)

    def test_matrices_roundtrip(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider
        from skeleton.persistence import restore_matrices, serialize_matrices

        jeeves = JeevesCore(provider=LocalEchoProvider())
        session = jeeves.open_session("persist-user")
        jeeves.ask(session.session_id, "forge builds blueprints for games")

        data = serialize_matrices(jeeves)
        fresh = JeevesCore(provider=LocalEchoProvider())
        restore_matrices(data, fresh)

        self.assertGreater(fresh.sam.stats()["terms"], 0)
        self.assertGreater(fresh.krem.stats()["concepts"], 0)


class TestGenesisPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_genesis_state_survives_restart(self):
        from skeleton.genesis import Genesis
        from skeleton.persistence import SnapshotStore, restore_genesis_state, snapshot_genesis_state

        store = SnapshotStore(self.tmp)

        # First boot: populate and snapshot
        g1 = Genesis(seed=42).boot()
        quad = g1.get("quad")
        quad.ingest_document("persist-doc", "The Forge produces blueprints for games.")
        g1.get("mag").record("ep-1", "first boot ran", tags=["boot"])
        captured = snapshot_genesis_state(g1, store=store)
        self.assertGreater(captured["planes"]["rag"], 0)
        self.assertGreater(captured["planes"]["kag"], 0)

        # Second boot: empty planes, then restore
        g2 = Genesis(seed=42).boot()
        self.assertEqual(g2.get("quad")._planes["kag"].graph.stats()["triples"], 0)
        restored = restore_genesis_state(g2, store=store)

        self.assertGreater(restored["rag"], 0)
        self.assertGreater(restored["kag"], 0)
        self.assertGreater(restored["mag"], 0)

        # Restored knowledge is queryable
        results = g2.get("quad").retrieve("what does the Forge produce?", k=5)
        self.assertIn("kag", {r.plane for r in results})
        self.assertGreater(len(g2.get("mag").recall_by_tag("boot")), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
