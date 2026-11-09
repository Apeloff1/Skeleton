"""Regression coverage for bounded retrieval hot-path state."""

from __future__ import annotations

from skeleton.retrieval.cache import ResultCache
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.index import InvertedIndex
from skeleton.retrieval.quad import QuadRetriever


def _result(fragment_id: str) -> ScoredResult:
    return ScoredResult(
        fragment_id=fragment_id,
        content=fragment_id,
        score=1.0,
        plane="rag",
    )


class _CountingPlane:
    def __init__(self) -> None:
        self.calls = 0
        self.added = []

    def query(self, query: str, top_k: int = 8):
        self.calls += 1
        return [_result(f"{query}-result")][:top_k]

    def add(self, chunk) -> None:
        self.added.append(chunk)


class _NoDocumentScanDict(dict):
    def items(self):
        raise AssertionError("search must use postings instead of scanning documents")


class _NoAggregateLengthDict(dict):
    def values(self):
        raise AssertionError("search must use the maintained total document length")


def test_result_cache_is_lru_and_hard_bounded() -> None:
    cache = ResultCache(ttl_s=60.0, max_entries=2)
    cache.put("a", (_result("a"),))
    cache.put("b", (_result("b"),))

    assert cache.get("a") is not None
    cache.put("c", (_result("c"),))

    assert cache.size() == 2
    assert cache.get("a") is not None
    assert cache.get("b") is None
    assert cache.get("c") is not None


def test_quad_retriever_reuses_cache_and_bounds_unique_queries() -> None:
    plane = _CountingPlane()
    retriever = QuadRetriever(cache=ResultCache(ttl_s=60.0, max_entries=8))
    retriever.register_plane("rag", plane)

    first = retriever.retrieve("hot-query")
    second = retriever.retrieve("hot-query")

    assert first == second
    assert plane.calls == 1
    assert retriever.stats()["cache_hits"] == 1

    for index in range(32):
        retriever.retrieve(f"unique-{index}")

    assert retriever.stats()["cache_size"] == 8


def test_quad_retriever_plane_history_stays_bounded_under_soak() -> None:
    plane = _CountingPlane()
    retriever = QuadRetriever()
    retriever.register_plane("rag", plane)

    for index in range(QuadRetriever._PLANE_HISTORY_LIMIT * 3):
        retriever.retrieve(f"soak-{index}", use_cache=False)

    stats = retriever.stats()
    assert len(stats["planes_used"]) == QuadRetriever._PLANE_HISTORY_LIMIT
    assert stats["planes_used"] == ["rag"] * QuadRetriever._PLANE_HISTORY_LIMIT


def test_ingest_invalidates_cached_rankings() -> None:
    plane = _CountingPlane()
    retriever = QuadRetriever(cache=ResultCache(ttl_s=60.0, max_entries=8))
    retriever.register_plane("rag", plane)

    retriever.retrieve("before-ingest")
    assert retriever.stats()["cache_size"] == 1

    assert retriever.ingest_document("doc-1", "new retrieval content") == 1
    assert retriever.stats()["cache_size"] == 0


def test_inverted_index_search_uses_postings_without_document_scans() -> None:
    index = InvertedIndex()
    index.add("a", "alpha alpha beta")
    index.add("b", "alpha beta beta beta")
    index.add("c", "gamma")

    # Search may inspect document count and individual lengths, but it must not
    # iterate every document or recompute the aggregate length on each query.
    index._docs = _NoDocumentScanDict(index._docs)
    index._doc_length = _NoAggregateLengthDict(index._doc_length)

    results = index.search("alpha alpha beta", top_k=2)

    assert [result.fragment_id for result in results] == ["a", "b"]
    assert [result.score for result in results] == [0.694388, 0.585462]
    assert [result.content for result in results] == [
        "alpha alpha beta",
        "alpha beta beta beta",
    ]
    assert all(result.plane == "index" for result in results)


def test_inverted_index_postings_and_length_track_replace_and_remove() -> None:
    index = InvertedIndex()
    index.add("a", "alpha beta beta")
    index.add("b", "gamma")

    assert index._total_doc_length == 4
    assert index._postings["beta"] == {"a": 2}

    index.add("a", "gamma gamma")
    assert index._total_doc_length == 3
    assert "alpha" not in index._postings
    assert "beta" not in index._postings
    assert index._postings["gamma"] == {"b": 1, "a": 2}
    assert index._df["gamma"] == 2

    assert index.remove("a") is True
    assert index._total_doc_length == 1
    assert index._postings["gamma"] == {"b": 1}
    assert index._df["gamma"] == 1
    assert index.remove("a") is False

    results = index.search("gamma")
    assert [result.fragment_id for result in results] == ["b"]
