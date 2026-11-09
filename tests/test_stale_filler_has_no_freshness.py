"""A stale filler does not keep a leftover freshness score."""

import pytest

from skeleton.memory.eviction import keep_score
from skeleton.memory.warmer import Filler


def _filler(key: str, ttl_s: int) -> Filler:
    return Filler(key=key, sha="abc", text=key, tokens=0, ttl_s=ttl_s, built_at=1_000, refreshed_at=1_000)


def test_stale_freshness_is_zero() -> None:
    now = 1_050.0
    fresh = keep_score(_filler("fresh", 100), now=now, hits=0)
    stale = keep_score(_filler("stale", 10), now=now, hits=0)
    assert fresh - stale == pytest.approx(1.0)
