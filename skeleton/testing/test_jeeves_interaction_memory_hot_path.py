from __future__ import annotations

import math

from skeleton.jeeves.agent.memory import MemoryNamespace
from skeleton.jeeves.agent.memory_game import (
    IndexCardStore,
    MemoryGameIndex,
    MemoryGamePolicy,
)


class _NoSortedNamespaceStore(IndexCardStore):
    def namespace_cards(self, *args, **kwargs):
        raise AssertionError("search hot path must use unsorted namespace scan")


class _CountingMemoryGameIndex(MemoryGameIndex):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tokenize_calls = 0
        self.activation_calls = 0

    def _tokens(self, text: str):
        self.tokenize_calls += 1
        return MemoryGameIndex._tokens(text)

    def activation(self, card, *, now=None):
        self.activation_calls += 1
        return super().activation(card, now=now)


def _fixture(card_count: int = 12):
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    store = _NoSortedNamespaceStore(max_cards=1000)
    index = _CountingMemoryGameIndex(
        store=store,
        policy=MemoryGamePolicy(max_hits=5, minimum_score=0.0),
        clock=lambda: 10_000.0,
    )
    for number in range(card_count):
        index.capture_interaction(
            namespace,
            f"compiler evidence trace {number}",
            trust=0.9,
            salience=0.8,
        )
    return namespace, index


def test_search_uses_precomputed_cue_tokens_and_unsorted_store_scan() -> None:
    namespace, index = _fixture(12)
    before_tokens = index.tokenize_calls

    hits = index.search(namespace, "compiler evidence", limit=3)

    assert len(hits) == 3
    assert index.tokenize_calls == before_tokens + 1


def test_search_computes_activation_once_per_scored_card() -> None:
    namespace, index = _fixture(9)
    before = index.activation_calls

    index.search(namespace, "compiler evidence", limit=4)

    assert index.activation_calls - before == 9


def test_bounded_ranking_preserves_best_score_order() -> None:
    namespace, index = _fixture(20)
    hits = index.search(namespace, "compiler evidence trace 19", limit=4)

    assert len(hits) == 4
    ordering = [
        (
            hit.score,
            hit.retrieval_probability,
            hit.card.updated_at,
            hit.card.card_id,
        )
        for hit in hits
    ]
    assert ordering == sorted(ordering, reverse=True)


def test_weighted_counter_cosine_contract_is_unchanged() -> None:
    left = MemoryGameIndex._tokens("alpha alpha beta")
    right = MemoryGameIndex._tokens("alpha beta beta beta")
    expected = 5.0 / ((5.0 ** 0.5) * (10.0 ** 0.5))

    assert math.isclose(MemoryGameIndex._cosine(left, right), expected)


def test_search_namespace_scan_never_walks_global_card_values() -> None:
    namespace, index = _fixture(8)
    other = MemoryNamespace("tenant", "other", "workspace", "session")
    for number in range(20):
        index.capture_interaction(
            other,
            f"other tenant memory {number}",
            trust=0.9,
            salience=0.8,
        )

    class _NoGlobalValues(dict):
        def values(self):
            raise AssertionError("interaction-memory search scanned global cards")

    index.store._cards = _NoGlobalValues(index.store._cards)
    hits = index.search(namespace, "compiler evidence", limit=3)

    assert len(hits) == 3
    assert all(hit.card.namespace.key == namespace.key for hit in hits)
