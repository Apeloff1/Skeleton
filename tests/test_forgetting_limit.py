"""An eviction limit of zero must not return every doomed memory."""

import pytest

from skeleton.memory.forgetting import ForgettingCurve


def test_limit_zero_is_empty_and_negative_is_rejected() -> None:
    curve = ForgettingCurve(retention_floor=0.99, half_life_s=1.0)
    curve.register("old", now=0.0)
    curve.register("older", now=0.0)
    assert curve.eviction_candidates(now=10_000.0, limit=0) == []
    assert len(curve.eviction_candidates(now=10_000.0, limit=1)) == 1
    with pytest.raises(ValueError):
        curve.eviction_candidates(now=10_000.0, limit=-1)
