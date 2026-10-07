"""The first readings are not a z-score of zero."""

import pytest

from skeleton.intelligence.surprise import OnlineGaussian, SurpriseError, SurpriseScorer


def test_warmup_does_not_score_zero() -> None:
    blank = OnlineGaussian()
    assert blank.variance is None
    assert blank.std is None
    assert blank.snapshot()["mean"] is None
    with pytest.raises(SurpriseError):
        blank.z_score(1.0)
    scorer = SurpriseScorer()
    with pytest.raises(SurpriseError):
        scorer.observe("queue", 1.0)
    with pytest.raises(SurpriseError):
        scorer.observe("queue", 1.0)
    reading = scorer.observe("queue", 5.0)
    assert reading.z != 0.0
    assert reading.surprise > 0
    with pytest.raises(SurpriseError):
        scorer.observe("queue", True)
