"""The in-process index must restart from exact, validated corpus state."""

import copy

import pytest

from skeleton.retrieval.index import InvertedIndex


def test_index_snapshot_round_trip_preserves_results_revision_and_digest() -> None:
    index = InvertedIndex(b=0.6, k1=1.2)
    index.add("b", "alpha beta")
    index.add("a", "alpha alpha")
    index.add("b", "beta gamma")
    state = index.snapshot()

    restored = InvertedIndex.from_snapshot(copy.deepcopy(state))

    assert restored.snapshot() == state
    assert restored.revision == index.revision
    assert restored.content_digest() == index.content_digest()
    assert [
        (row.fragment_id, row.score)
        for row in restored.search("alpha beta", top_k=10)
    ] == [
        (row.fragment_id, row.score)
        for row in index.search("alpha beta", top_k=10)
    ]


def test_index_digest_is_insertion_order_independent() -> None:
    left = InvertedIndex()
    left.add("a", "alpha")
    left.add("b", "beta")

    right = InvertedIndex()
    right.add("b", "beta")
    right.add("a", "alpha")

    assert left.content_digest() == right.content_digest()


def test_index_revision_tracks_mutating_operations() -> None:
    index = InvertedIndex()
    assert index.revision == 0
    index.add("a", "alpha")
    assert index.revision == 1
    index.add("a", "beta")
    assert index.revision == 2
    assert index.remove("missing") is False
    assert index.revision == 2
    assert index.remove("a") is True
    assert index.revision == 3


def test_index_snapshot_rejects_digest_tampering() -> None:
    index = InvertedIndex()
    index.add("a", "alpha")
    state = index.snapshot()
    state["documents"][0]["text"] = "tampered"

    with pytest.raises(ValueError, match="digest mismatch"):
        InvertedIndex.from_snapshot(state)


def test_index_snapshot_rejects_unknown_version() -> None:
    index = InvertedIndex()
    state = index.snapshot()
    state["version"] = 999
    with pytest.raises(ValueError, match="unsupported"):
        InvertedIndex.from_snapshot(state)


def test_index_freshness_is_bound_to_exact_corpus_digest() -> None:
    index = InvertedIndex()
    index.add("a", "alpha")
    state = index.freshness_state(
        source_revision="source-1",
        indexed_at=100.0,
        stale_after_s=60.0,
    )

    assert state.index_version == index.content_digest()
    assert state.source_revision == "source-1"
    assert state.stale(159.9) is False
    assert state.stale(160.0) is True
