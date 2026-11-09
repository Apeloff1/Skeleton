import pytest

from skeleton.perf_profiler.clock import DeterministicClock
from skeleton.perf_profiler.frames import FrameSampler


def test_mark_uses_injected_clock_and_detects_hitch():
    clock = DeterministicClock(script=[16.0, 16.0, 50.0, 16.0])
    sampler = FrameSampler(budget_ms=16.667, clock=clock)
    assert sampler.mark() is None
    results = [sampler.mark() for _ in range(4)]
    assert [r is not None for r in results] == [False, False, True, False]
    hitch = results[2]
    assert hitch.frame_index == 2 and hitch.frame_ms == 50.0
    assert hitch.over_ms == pytest.approx(50.0 - 16.667)
    assert sampler.window == (16.0, 16.0, 50.0, 16.0)


def test_ring_buffer_keeps_last_capacity_frames():
    sampler = FrameSampler(budget_ms=10, capacity=3)
    for v in [1, 2, 30, 4, 5]:
        sampler.record(v)
    assert sampler.window == (30.0, 4.0, 5.0)
    stats = sampler.stats()
    assert stats.frames == 5 and stats.window == 3
    assert stats.hitch_count == 1
    assert stats.hitch_ratio == pytest.approx(1 / 3)
    assert stats.worst_ms == 30.0


def test_stats_use_main_profiler_percentiles():
    sampler = FrameSampler(budget_ms=100, capacity=100)
    for v in range(1, 101):
        sampler.record(float(v))
    pct = sampler.stats().percentiles
    assert pct["samples"] == 100
    assert pct["p50_ms"] == 51.0
    assert pct["p95_ms"] == 96.0
    assert pct["p99_ms"] == 100.0


def test_hitch_factor_raises_threshold():
    sampler = FrameSampler(budget_ms=10, hitch_factor=2.0)
    assert sampler.record(19.9) is None
    assert sampler.record(20.1) is not None


def test_hitch_log_is_bounded():
    sampler = FrameSampler(budget_ms=1, max_hitches=2)
    for _ in range(5):
        sampler.record(5)
    assert len(sampler.hitches) == 2
    assert [h.frame_index for h in sampler.hitches] == [3, 4]


def test_empty_window_fails_closed():
    stats = FrameSampler().stats()
    assert stats.window == 0
    assert not stats.within_budget(1.0)
    assert stats.percentiles["samples"] == 0


def test_within_budget_uses_ratio():
    sampler = FrameSampler(budget_ms=10)
    for v in [5, 5, 5, 50]:
        sampler.record(v)
    assert not sampler.stats().within_budget(0.0)
    assert sampler.stats().within_budget(0.25)


def test_reset_clears_state():
    clock = DeterministicClock(script=[40.0])
    sampler = FrameSampler(budget_ms=10, clock=clock)
    sampler.mark()
    sampler.mark()
    sampler.reset()
    assert sampler.window == () and sampler.hitches == () and sampler.stats().frames == 0
    assert sampler.mark() is None


@pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), "3", True])
def test_record_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        FrameSampler().record(bad)


@pytest.mark.parametrize("kwargs", [{"budget_ms": 0}, {"capacity": 0}, {"hitch_factor": 0.5}, {"max_hitches": 0}])
def test_constructor_validation(kwargs):
    with pytest.raises(ValueError):
        FrameSampler(**kwargs)
