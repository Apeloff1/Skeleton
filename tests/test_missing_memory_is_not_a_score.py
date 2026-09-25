"""A missing memory is not forgotten-with-score-zero, and it is not perfectly retained."""

import pytest

from skeleton.memory.forgetting import ForgettingCurve, ForgettingError
from skeleton.memory.repetition import RepetitionScheduler


def test_missing_memory_is_not_scored() -> None:
    curve = ForgettingCurve()
    with pytest.raises(ForgettingError):
        curve.score("missing")
    with pytest.raises(ForgettingError):
        curve.register("flag", importance=True)
    curve.register("kept", importance=0.0, salience=0.0, now=10.0)
    assert 0.0 <= curve.score("kept", now=10.0) <= 1.0
    scheduler = RepetitionScheduler(clock=lambda: 1_000.0)
    assert scheduler.stats()["mean_stability_h"] is None
    with pytest.raises(ValueError):
        scheduler.retention("missing")
    scheduler.enroll("ep")
    assert 0.0 < scheduler.retention("ep") <= 1.0
