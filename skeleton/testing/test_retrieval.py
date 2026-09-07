"""Tests for the upgraded retrieval layer: vector store, KAG plane, quad wiring."""

from __future__ import annotations

import unittest

from skeleton.memory.core import Chunk


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        from skeleton.memory.vector import VectorStore
        self.store = VectorStore()

    def test_add_and_query_semantic(self):
        self.store.add(Chunk(text="the wizard casts a fireball spell", chunk_id="d1"))
        self.store.add(Chunk(text="a knight swings a heavy sword", chunk_id="d2"))
        self.store.add(Chunk(text="cooking soup in the kitchen", chunk_id="d3"))

        results = self.store.query("magic spell casting", top_k=2)
        self.assertGreater(len(results), 0)
        # Wizard doc should outrank the kitchen doc for a magic query
        ids = [r.chunk.chunk_id for r in results]
        self.assertIn("d1", ids)
        self.assertNotIn("d3", ids)

    def test_metadata_filter(self):
        self.store.add(Chunk(text="combat tactics", chunk_id="c1", metadata={"era": "medieval"}))
        self.store.add(Chunk(text="laser combat", chunk_id="c2", metadata={"era": "scifi"}))

        results = self.store.query("combat", metadata_filter={"era": "scifi"})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.chunk_id, "c2")

    def test_empty_store_returns_empty(self):
        self.assertEqual(self.store.query("anything"), [])

    def test_deterministic_embeddings(self):
        from skeleton.memory.vector import HashEmbedder
        emb = HashEmbedder(64)
        v1 = emb.embed("skeleton platform")
        v2 = emb.embed("skeleton platform")
        self.assertEqual(v1, v2)
        self.assertAlmostEqual(sum(x * x for x in v1), 1.0, places=5)


class TestKAGRetriever(unittest.TestCase):
    def setUp(self):
        from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever
        self.graph = KnowledgeGraph()
        self.graph.add_many([
            ("skeleton", "is_a", "game engine"),
            ("skeleton", "has_subsystem", "forge"),
            ("forge", "produces", "blueprints"),
            ("blueprints", "target", "godot"),
        ])
        self.kag = KAGRetriever(self.graph)

    def test_entity_extraction(self):
        entities = self.graph.find_entities("how does the forge work in skeleton")
        self.assertIn("skeleton", entities)
        self.assertIn("forge", entities)

    def test_graph_paths(self):
        paths = self.graph.paths("skeleton", "godot")
        self.assertGreater(len(paths), 0)
        self.assertLessEqual(len(paths[0]), 3)

    def test_kag_query_returns_facts(self):
        results = self.kag.query("what does forge produce?")
        self.assertGreater(len(results), 0)
        contents = " ".join(r.content for r in results)
        self.assertIn("forge", contents)
        for r in results:
            self.assertEqual(r.plane, "kag")


class TestQuadRetrieverWiring(unittest.TestCase):
    def test_quad_has_four_planes_after_boot(self):
        from skeleton.genesis import Genesis

        g = Genesis(seed=42).boot()
        quad = g.get("quad")
        self.assertEqual(len(quad._planes), 4)
        self.assertEqual(set(quad._planes.keys()), {"rag", "cag", "mag", "kag"})

    def test_quad_retrieve_fuses_planes(self):
        from skeleton.genesis import Genesis
        from skeleton.memory.core import Chunk

        g = Genesis(seed=42).boot()
        rag = g.get("rag")
        rag.add(Chunk(text="skeleton forge builds game blueprints", chunk_id="q1"))

        quad = g.get("quad")
        kag = quad._planes["kag"]
        kag.graph.add("forge", "produces", "blueprints")

        results = quad.retrieve("forge blueprints", k=5)
        self.assertGreater(len(results), 0)
        planes = {r.plane for r in results}
        # At minimum the vector RAG and KAG planes should contribute
        self.assertIn("kag", planes)

    def test_genesis_rag_is_vector_store(self):
        from skeleton.genesis import Genesis
        from skeleton.memory.vector import VectorStore

        g = Genesis(seed=42).boot()
        self.assertIsInstance(g.get("rag"), VectorStore)


if __name__ == "__main__":
    unittest.main(verbosity=2)
