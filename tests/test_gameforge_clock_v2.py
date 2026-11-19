import pytest

from skeleton.frontier.gameforge_clock_v2 import MonotonicClock


def test_clock_advances_deterministically():
    clock = MonotonicClock(10)
    assert clock.now == 10
    assert clock.advance(5) == 15
    assert clock.set(20) == 20


def test_clock_rejects_regression():
    clock = MonotonicClock(10)
    with pytest.raises(ValueError, match="backwards"):
        clock.set(9)


def test_clock_rejects_negative_advance():
    clock = MonotonicClock()
    with pytest.raises(ValueError, match="non-negative"):
        clock.advance(-1)
