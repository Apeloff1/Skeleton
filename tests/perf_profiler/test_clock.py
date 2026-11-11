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


@pytest.mark.parametrize("bad", [10**1000, True, "100", float("nan")])
def test_clock_rejects_unbounded_timestamps_and_deltas(bad):
    with pytest.raises(ValueError, match="finite"):
        DeterministicClock(start_ms=bad)
    with pytest.raises(ValueError, match="finite"):
        DeterministicClock().advance(bad)
    with pytest.raises(ValueError, match="finite"):
        DeterministicClock(script=[bad])


def test_clock_overflow_is_atomic_for_manual_and_scripted_advance():
    clock = DeterministicClock(start_ms=1e308)
    with pytest.raises(ValueError, match="finite bound"):
        clock.advance(1e308)
    assert clock.now_ms() == 1e308

    scripted = DeterministicClock(start_ms=1e308, script=[1e308])
    assert scripted.now_ms() == 1e308
    with pytest.raises(ValueError, match="finite bound"):
        scripted.now_ms()
    assert scripted.remaining_script == 1
