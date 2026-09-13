import pytest
from skeleton.frontier.gameforge_clock import LogicalClock

def test_clock_ticks_monotonically():
    c = LogicalClock(4)
    assert c.tick() == 5
    assert c.tick(3) == 8

def test_clock_rejects_non_positive_ticks():
    with pytest.raises(ValueError): LogicalClock().tick(0)
