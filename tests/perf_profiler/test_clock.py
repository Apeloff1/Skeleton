import pytest

from skeleton.perf_profiler.clock import DeterministicClock, MonotonicClock


def test_deterministic_clock_only_moves_when_told():
    clock = DeterministicClock(start_ms=5.0)
    assert clock.now_ms() == 5.0
    assert clock.now_ms() == 5.0
    assert clock.advance(2.5) == 7.5
    assert clock.now_ms() == 7.5


def test_script_deltas_apply_after_first_read():
    clock = DeterministicClock(script=[10.0, 3.0])
    assert clock.now_ms() == 0.0
    assert clock.now_ms() == 10.0
    assert clock.now_ms() == 13.0
    assert clock.remaining_script == 0
    assert clock.now_ms() == 13.0


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), True])
def test_rejects_backwards_or_non_finite(bad):
    with pytest.raises(ValueError):
        DeterministicClock().advance(bad)
    with pytest.raises(ValueError):
        DeterministicClock(script=[bad])


def test_monotonic_clock_is_non_decreasing():
    clock = MonotonicClock()
    a = clock.now_ms()
    assert clock.now_ms() >= a
