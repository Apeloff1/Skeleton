from __future__ import annotations

import pytest

from knowledge_nexus.engines.aaahrage_hybrid_rag_engine import AAAHRAGHybridEngine


def _doc_ids(results):
    return [result.metadata["doc_id"] for result in results]


def test_hybrid_retrieves_indexed_documents_and_ranks_specific_match() -> None:
    engine = AAAHRAGHybridEngine()
    engine.index_document(
        "python-cache",
        "Python cache optimization reduces repeated computation.",
        {"source": "runtime-guide"},
    )
    engine.index_document(
        "garden",
        "Garden flowers need water and sunlight.",
        {"source": "garden-guide"},
    )

    results = engine.retrieve("python cache", method="hybrid", top_k=2)

    assert _doc_ids(results) == ["python-cache"]
    assert results[0].source == "runtime-guide"
    assert results[0].score > 0.9
    assert results[0].retrieval_method == "hybrid"


def test_reindex_removes_stale_postings_and_invalidates_cache() -> None:
    engine = AAAHRAGHybridEngine()
    engine.index_document("doc", "legacy token payload")

    assert _doc_ids(engine.retrieve("legacy", method="hybrid")) == ["doc"]
    assert _doc_ids(engine.retrieve("legacy", method="hybrid")) == ["doc"]
    assert engine.usage_stats["cache_hits"] == 1

    engine.index_document("doc", "modern replacement payload")

    assert engine.cache == {}
    assert engine.retrieve("legacy", method="hybrid") == []
    assert _doc_ids(engine.retrieve("modern", method="hybrid")) == ["doc"]


def test_agentic_graph_expansion_surfaces_linked_document() -> None:
    engine = AAAHRAGHybridEngine()
    engine.index_document(
        "overview",
        "Distributed systems overview and architecture.",
        {"links": ["consensus"]},
    )
    engine.index_document(
        "consensus",
        "Quorum internals, leader election, and commit safety.",
    )

    hybrid = engine.retrieve("distributed systems", method="hybrid", top_k=2)
    agentic = engine.retrieve("distributed systems", method="agentic", top_k=2)

    assert _doc_ids(hybrid) == ["overview"]
    assert set(_doc_ids(agentic)) == {"overview", "consensus"}
    linked = next(row for row in agentic if row.metadata["doc_id"] == "consensus")
    assert linked.metadata["graph_hop"] == 1
    assert linked.metadata["via"] == "overview"


def test_combined_mode_deduplicates_documents_across_lanes() -> None:
    engine = AAAHRAGHybridEngine()
    engine.index_document(
        "root",
        "retrieval graph knowledge",
        {"links": ["detail"]},
    )
    engine.index_document("detail", "retrieval detail")

    results = engine.retrieve("retrieval", method="combined", top_k=10)
    doc_ids = _doc_ids(results)

    assert len(doc_ids) == len(set(doc_ids))
    assert set(doc_ids) == {"root", "detail"}


@pytest.mark.parametrize("method", ["", "vector", "unknown"])
def test_retrieve_rejects_unknown_method(method: str) -> None:
    engine = AAAHRAGHybridEngine()
    engine.index_document("doc", "content")

    with pytest.raises(ValueError, match="unsupported retrieval method"):
        engine.retrieve("content", method=method)


def test_non_positive_top_k_short_circuits_without_retrieval_work() -> None:
    engine = AAAHRAGHybridEngine()
    engine.index_document("doc", "content")

    assert engine.retrieve("content", top_k=0) == []
    assert engine.usage_stats["agentic_hits"] == 0
    assert engine.usage_stats["hybrid_hits"] == 0
