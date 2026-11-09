"""KnowledgeGraph.add_many counts newly stored triples, not replayed rows."""

from skeleton.retrieval.kag import KnowledgeGraph


def test_add_many_ignores_duplicate_facts() -> None:
    graph = KnowledgeGraph()
    first = graph.add_many([("Ada", "wrote", "Notes"), ("Ada", "wrote", "Notes")])
    second = graph.add_many([("Ada", "wrote", "Notes"), ("Grace", "wrote", "Compiler")])
    assert first == 1
    assert second == 1
    assert graph.stats()["triples"] == 2
