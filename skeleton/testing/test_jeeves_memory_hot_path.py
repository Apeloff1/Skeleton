from __future__ import annotations

from skeleton.jeeves.agent.memory import (
    InMemoryStore,
    MemoryNamespace,
    MemoryRecord,
    MemoryRetriever,
)
from skeleton.jeeves.agent.types import MemoryKind, stable_id


class _NoSortedListStore(InMemoryStore):
    def list_namespace(self, *args, **kwargs):
        raise AssertionError("retrieval hot path must use unsorted namespace scan")


class _CountingMemoryRetriever(MemoryRetriever):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tokenize_calls = 0

    def _tokens(self, text: str):
        self.tokenize_calls += 1
        return MemoryRetriever._tokens(text)


def _record(namespace: MemoryNamespace, name: str, content: str) -> MemoryRecord:
    return MemoryRecord(
        memory_id=stable_id("memory", {"name": name}),
        namespace=namespace,
        kind=MemoryKind.EPISODIC,
        content=content,
        created_at=100.0,
        updated_at=100.0,
        salience=0.8,
        trust=0.9,
        tags=("compiler", "evidence"),
    )


def _retriever():
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    store = _NoSortedListStore(clock=lambda: 100.0)
    for name, content in (
        ("a", "deterministic compiler evidence graph"),
        ("b", "compiler provenance replay receipt"),
        ("c", "unrelated scene observation"),
    ):
        store.put(_record(namespace, name, content))
    return namespace, store, _CountingMemoryRetriever(store, clock=lambda: 100.0)


def test_memory_retrieval_reuses_cached_record_tokenization_and_skips_presort() -> None:
    namespace, _store, retriever = _retriever()

    first = retriever.search(namespace, "compiler evidence", limit=3)
    calls_after_first = retriever.tokenize_calls
    second = retriever.search(namespace, "compiler evidence", limit=3)

    assert [hit.record.memory_id for hit in second] == [
        hit.record.memory_id for hit in first
    ]
    assert retriever.tokenize_calls == calls_after_first + 1
    stats = retriever.retrieval_stats()
    assert stats["searches"] == 2
    assert stats["lexical_cache_misses"] == 3
    assert stats["lexical_cache_hits"] == 3
    assert stats["lexical_cache_entries"] == 3


def test_memory_retrieval_cache_is_content_sensitive() -> None:
    namespace, store, retriever = _retriever()
    retriever.search(namespace, "compiler evidence", limit=3)
    before = retriever.retrieval_stats()

    replacement = _record(namespace, "a", "new counterfactual compiler trace")
    store.put(replacement)
    retriever.search(namespace, "counterfactual trace", limit=3)
    after = retriever.retrieval_stats()

    assert after["lexical_cache_misses"] == before["lexical_cache_misses"] + 1
    assert after["lexical_cache_hits"] >= before["lexical_cache_hits"] + 2
