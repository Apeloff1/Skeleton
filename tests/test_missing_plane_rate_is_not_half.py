"""A prefix with no evidence is not scored as one half."""

import pytest

from skeleton.intelligence.prefix_improve import AnswerQualitySignal, adapt_plane_learner


class _Variant:
    sha = "abc"


def test_missing_rates_are_not_half() -> None:
    score = adapt_plane_learner(None)
    with pytest.raises(ValueError):
        score(_Variant())
    learner = type("Learner", (), {"stats": lambda self: {"rates": {}}})()
    with pytest.raises(ValueError):
        adapt_plane_learner(learner)(_Variant())
    signal = AnswerQualitySignal()
    with pytest.raises(ValueError):
        signal.record("abc", True)
    signal.record("abc", 0.2)
    signal.record("abc", 0.4)
    scored = adapt_plane_learner(None, signal=signal)
    assert scored(_Variant()) == pytest.approx(0.3)
