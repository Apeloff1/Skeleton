"""Tests for Jeeves KAG citations."""

from __future__ import annotations

import unittest


class TestCitationEngine(unittest.TestCase):
    def _engine(self):
        from skeleton.jeeves.citations import CitationEngine
        from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever

        graph = KnowledgeGraph()
        graph.add_many([
            ("skeleton", "is_a", "game engine"),
            ("skeleton", "has_subsystem", "forge"),
            ("forge", "produces", "blueprints"),
            ("blueprints", "target", "godot"),
        ])
        return CitationEngine(KAGRetriever(graph))

    def test_cite_finds_supporting_triples(self):
        engine = self._engine()
        citations = engine.cite("what does the forge produce?")
        self.assertGreater(len(citations), 0)
        facts = " ".join(c.render() for c in citations)
        self.assertIn("forge", facts)

    def test_citations_ranked_by_entity_order(self):
        engine = self._engine()
        citations = engine.cite("forge blueprints")
        if len(citations) >= 2:
            self.assertGreaterEqual(citations[0].score, citations[-1].score)

    def test_no_graph_returns_empty(self):
        from skeleton.jeeves.citations import CitationEngine
        engine = CitationEngine(kag=None)
        self.assertEqual(engine.cite("anything"), [])

    def test_context_terms_extend_reach(self):
        engine = self._engine()
        plain = engine.cite("tell me more")
        with_ctx = engine.cite("tell me more", context_terms=["forge"])
        self.assertGreater(len(with_ctx), len(plain))

    def test_appendix_format(self):
        engine = self._engine()
        citations = engine.cite("skeleton forge")
        appendix = engine.format_appendix(citations)
        self.assertIn("Sources (knowledge graph):", appendix)
        self.assertIn("[1]", appendix)

    def test_max_citations_respected(self):
        from skeleton.jeeves.citations import CitationEngine
        from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever

        graph = KnowledgeGraph()
        for i in range(10):
            graph.add("hub", f"rel_{i}", f"leaf_{i}")
        engine = CitationEngine(KAGRetriever(graph), max_citations=3)
        self.assertEqual(len(engine.cite("hub")), 3)


class TestCitationsInJeeves(unittest.TestCase):
    def test_ask_returns_citations_when_graph_has_facts(self):
        from skeleton.jeeves import JeevesCore
        from skeleton.jeeves.providers import LocalEchoProvider
        from skeleton.retrieval.kag import KnowledgeGraph, KAGRetriever

        graph = KnowledgeGraph()
        graph.add("forge", "produces", "blueprints")

        class FakeQuad:
            _planes = {"kag": KAGRetriever(graph)}
            def retrieve(self, q, k=3):
                return []

        jeeves = JeevesCore(provider=LocalEchoProvider(), retriever=FakeQuad())
        session = jeeves.open_session("cite-user")
        reply = jeeves.ask(session.session_id, "what does forge produce?")
        self.assertIn("citations", reply)
        self.assertGreater(len(reply["citations"]), 0)
        self.assertEqual(reply["citations"][0]["matched_entity"], "forge")


if __name__ == "__main__":
    unittest.main(verbosity=2)
