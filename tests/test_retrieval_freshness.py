"""Freshness metadata remains truthful across cache reuse and stale transitions."""

import copy

from skeleton.retrieval.freshness import FreshnessRegistry
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.quad import QuadRetriever


class _Clock:
    def __init__(self, value: float) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class _Plane:
    def __init__(self) -> None:
        self.calls = 0

    def query(self, query: str, top_k: int):
        self.calls += 1
        return [ScoredResult("doc", query, 1.0, plane="rag")]


def test_freshness_cache_token_changes_when_stale_boundary_crosses() -> None:
    clock = _Clock(100.0)
    registry = FreshnessRegistry(clock=clock)
    registry.update(
        "rag",
        index_version="idx-1",
        source_revision="rev-a",
        indexed_at=100.0,
        stale_after_s=10.0,
    )

    fresh = registry.cache_token()
    clock.value = 109.0
    assert registry.cache_token() == fresh
    clock.value = 110.0
    assert registry.cache_token() != fresh


def test_cached_result_refreshes_age_without_requery_before_stale_boundary() -> None:
    clock = _Clock(100.0)
    registry = FreshnessRegistry(clock=clock)
    registry.update(
        "rag",
        index_version="idx-1",
        source_revision="rev-a",
        indexed_at=100.0,
        stale_after_s=100.0,
    )
    plane = _Plane()
    quad = QuadRetriever(freshness=registry)
    quad.register_plane("rag", plane)

    first = quad.retrieve("alpha")
    clock.value = 125.0
    second = quad.retrieve("alpha")

    assert plane.calls == 1
    assert first[0].metadata["fusion_freshness"]["rag"]["age_s"] == 0.0
    assert second[0].metadata["fusion_freshness"]["rag"]["age_s"] == 25.0
    assert second[0].metadata["stale"] is False


def test_stale_transition_invalidates_cache_identity_and_requeries() -> None:
    clock = _Clock(100.0)
    registry = FreshnessRegistry(clock=clock)
    registry.update(
        "rag",
        index_version="idx-1",
        source_revision="rev-a",
        indexed_at=100.0,
        stale_after_s=5.0,
    )
    plane = _Plane()
    quad = QuadRetriever(freshness=registry)
    quad.register_plane("rag", plane)

    quad.retrieve("alpha")
    clock.value = 106.0
    stale = quad.retrieve("alpha")

    assert plane.calls == 2
    assert stale[0].metadata["stale"] is True
    assert quad.stats()["stale_results"] >= 1


def test_freshness_registry_checkpoint_round_trip() -> None:
    clock = _Clock(50.0)
    registry = FreshnessRegistry(clock=clock)
    registry.update(
        "rag",
        index_version="idx-7",
        source_revision="rev-7",
        indexed_at=40.0,
        stale_after_s=20.0,
    )
    state = registry.snapshot()

    restored = FreshnessRegistry.from_snapshot(copy.deepcopy(state), clock=clock)

    assert restored.snapshot() == state
    assert restored.metadata("rag")["age_s"] == 10.0
    assert restored.metadata("rag")["stale"] is False
