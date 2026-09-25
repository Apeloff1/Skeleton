"""Seeing a pattern twice must raise confidence above seeing it once."""

import pytest

from skeleton.intelligence.temporal import TemporalEvent, TemporalReasoner


def test_repeated_pattern_crosses_the_confidence_floor() -> None:
    reasoner = TemporalReasoner()
    pattern = ["wake", "eat", "work"]
    reasoner.learn_pattern(pattern)
    assert reasoner.predict_next(["wake", "eat"], confidence_threshold=0.7) == []
    reasoner.learn_pattern(pattern)
    predicted = reasoner.predict_next(["wake", "eat"], confidence_threshold=0.7)
    assert predicted and predicted[0][0] == "work"
    assert predicted[0][1] == 1.0
    with pytest.raises(ValueError):
        reasoner.learn_pattern(["only"])


def test_negative_duration_is_rejected() -> None:
    event = TemporalEvent("a", "start", 0.0, duration=-1.0)
    other = TemporalEvent("b", "end", 1.0, duration=1.0)
    with pytest.raises(ValueError):
        event.overlaps(other)
