"""A pack with no era is not planned as extraction_now."""

import pytest

from skeleton.jeeves.builder import BuilderBrain, _mix_of


class _Left:
    def __init__(self, numbers):
        self.numbers = numbers


def test_missing_era_and_a_boolean_count_are_refused() -> None:
    with pytest.raises(ValueError):
        BuilderBrain().plan({})
    with pytest.raises(ValueError):
        BuilderBrain().plan({"era": True})
    assert _mix_of(_Left((True, 1, 0))) is None
    assert _mix_of(_Left((2, 1, 0))) == (2, 1, 0)
