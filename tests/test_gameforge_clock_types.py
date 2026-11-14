import pytest

from skeleton.frontier.gameforge_clock import LogicalClock


def test_clock_rejects_boolean_start():
    with pytest.raises(ValueError):
        LogicalClock(True)


def test_clock_rejects_invalid_tick_amount():
    clock = LogicalClock()
    with pytest.raises(ValueError):
        clock.tick(True)
    with pytest.raises(ValueError):
        clock.tick(0)


def test_clock_is_monotonic():
    clock = LogicalClock(3)
    assert clock.tick(2) == 5
