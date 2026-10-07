"""Configured forgetting half-life must change retrievability."""

import math

import pytest

from skeleton.memory.forgetting import ForgettingCurve, ForgettingError, MemoryTrace, retrievability


def test_shorter_half_life_forgets_faster() -> None:
    now = 1_000_000.0
    trace = MemoryTrace(
        memory_id="episode",
        created_at=now - 86_400,
        last_recalled_at=now - 86_400,
        importance=0.0,
        salience=0.0,
    )

    fast = retrievability(trace, now, half_life_s=86_400)
    slow = retrievability(trace, now, half_life_s=86_400 * 4)

    assert fast == pytest.approx(math.exp(-1.0))
    assert slow > fast


def test_curve_evicts_using_its_own_half_life() -> None:
    now = 1_000_000.0
    short = ForgettingCurve(half_life_s=100.0, retention_floor=0.5)
    long = ForgettingCurve(half_life_s=100_000.0, retention_floor=0.5)
    short.register("a", importance=0.0, salience=0.0, now=now - 10_000)
    long.register("a", importance=0.0, salience=0.0, now=now - 10_000)

    assert short.score("a", now) < 0.5
    assert long.score("a", now) > 0.5
    assert [item.memory_id for item in short.eviction_candidates(now)] == ["a"]
    assert long.eviction_candidates(now) == []
    assert short.snapshot(now)["a"]["retrievability"] == pytest.approx(short.score("a", now))


def test_non_positive_half_life_is_rejected() -> None:
    with pytest.raises(ForgettingError):
        ForgettingCurve(half_life_s=0)
    trace = MemoryTrace("m", created_at=0.0, last_recalled_at=0.0)
    with pytest.raises(ForgettingError):
        retrievability(trace, 1.0, half_life_s=-5)
