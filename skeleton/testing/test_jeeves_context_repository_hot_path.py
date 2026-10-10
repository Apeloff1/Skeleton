from __future__ import annotations

from skeleton.jeeves.agent.context_repository import (
    ContextEntry,
    ContextKind,
    ContextNamespace,
    ContextPatch,
    ContextPatchItem,
    ContextRepository,
    PatchOperation,
)
from skeleton.jeeves.agent.types import stable_id


class _CountingContextRepository(ContextRepository):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tokenize_calls = 0
        self.checkout_calls: list[bool] = []

    def checkout(self, branch: str = "main", *, include_tombstones: bool = True):
        self.checkout_calls.append(include_tombstones)
        return super().checkout(branch, include_tombstones=include_tombstones)

    def _tokens(self, text: str):
        self.tokenize_calls += 1
        return ContextRepository._tokens(text)


def _entry(namespace: ContextNamespace, key: str, content: str) -> ContextEntry:
    return ContextEntry(
        entry_id=stable_id("entry", {"key": key}),
        namespace=namespace,
        key=key,
        kind=ContextKind.EPISODIC,
        content=content,
        created_at=100.0,
        updated_at=100.0,
        confidence=0.9,
        salience=0.8,
        trust=0.95,
        tags=("compiler", "evidence"),
    )


def _repository() -> _CountingContextRepository:
    namespace = ContextNamespace("tenant", "user", "workspace")
    repository = _CountingContextRepository(namespace, clock=lambda: 100.0)
    entries = (
        _entry(namespace, "a", "deterministic compiler evidence graph"),
        _entry(namespace, "b", "compiler replay provenance receipts"),
        _entry(namespace, "c", "unrelated visual note"),
    )
    patch = ContextPatch(
        patch_id=stable_id(
            "patch",
            {"entries": [entry.content_fingerprint for entry in entries]},
        ),
        namespace=namespace,
        items=tuple(
            ContextPatchItem(PatchOperation.UPSERT, entry.key, entry=entry, reason="fixture")
            for entry in entries
        ),
        author="test",
        created_at=100.0,
        rationale="fixture",
    )
    repository.commit("main", patch, message="fixture", expected_head=None)
    return repository


def test_context_retrieval_reuses_cached_entry_tokenization() -> None:
    repository = _repository()

    repository.checkout_calls.clear()
    first = repository.retrieve("compiler evidence", max_entries=3)
    assert repository.checkout_calls == [True]
    calls_after_first = repository.tokenize_calls
    second = repository.retrieve("compiler evidence", max_entries=3)

    assert [hit.entry.key for hit in second] == [hit.entry.key for hit in first]
    assert repository.tokenize_calls == calls_after_first + 1
    stats = repository.retrieval_stats()
    assert stats["retrievals"] == 2
    assert stats["lexical_cache_misses"] == 3
    assert stats["lexical_cache_hits"] == 3
    assert stats["lexical_cache_entries"] == 3


def test_context_retrieval_cache_is_content_sensitive() -> None:
    repository = _repository()
    repository.retrieve("compiler evidence", max_entries=3)
    before = repository.retrieval_stats()
    namespace = repository.namespace
    replacement = _entry(namespace, "a", "new compiler evidence with counterfactual trace")
    patch = ContextPatch(
        patch_id=stable_id("patch", {"replacement": replacement.content_fingerprint}),
        namespace=namespace,
        items=(
            ContextPatchItem(
                PatchOperation.UPSERT,
                "a",
                entry=replacement,
                reason="update",
            ),
        ),
        author="test",
        created_at=100.0,
        rationale="update",
    )
    repository.commit("main", patch, message="update", expected_head=repository.head())

    repository.retrieve("counterfactual trace", max_entries=3)
    after = repository.retrieval_stats()
    assert after["lexical_cache_misses"] == before["lexical_cache_misses"] + 1
    assert after["lexical_cache_hits"] >= before["lexical_cache_hits"] + 2
