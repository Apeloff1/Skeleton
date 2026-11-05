import pytest

from skeleton.gameforge.batch_b071 import ClockError, DeterministicRng, EventScheduler, SimClock, SimContext


def test_clock_advances_and_rejects_backwards():
    c = SimClock(tick_ns=10)
    assert c.advance(3) == 3 and c.now_ns == 30
    with pytest.raises(ClockError):
        c.advance(-1)


def test_frozen_clock_refuses():
    c = SimClock()
    c.freeze()
    with pytest.raises(ClockError):
        c.advance()
    c.thaw()
    assert c.advance() == 1


def test_rng_reproducible_and_forks_independent():
    a, b = DeterministicRng(7), DeterministicRng(7)
    assert [a.randint(0, 99) for _ in range(5)] == [b.randint(0, 99) for _ in range(5)]
    f1 = DeterministicRng(7).fork("ai")
    _ = DeterministicRng(7).fork("physics").random()
    assert f1.random() == DeterministicRng(7).fork("ai").random()
    assert DeterministicRng(7).fork("ai").seed != DeterministicRng(7).fork("x").seed


def test_rng_rejects_bad_seed_and_empty_choice():
    with pytest.raises(ClockError):
        DeterministicRng(-1)
    with pytest.raises(ClockError):
        DeterministicRng(1).choice([])


def test_scheduler_orders_by_tick_priority_seq():
    c = SimClock()
    s = EventScheduler(c)
    out = []
    s.schedule(2, "late", lambda: out.append("late"))
    s.schedule(1, "b", lambda: out.append("b"), priority=1)
    s.schedule(1, "a", lambda: out.append("a"), priority=0)
    s.schedule(1, "a2", lambda: out.append("a2"), priority=0)
    assert s.run_until(5) == 4
    assert out == ["a", "a2", "b", "late"] and c.tick == 5


def test_scheduler_rejects_past():
    s = EventScheduler(SimClock(start_tick=3))
    with pytest.raises(ClockError):
        s.schedule(-1, "x", lambda: None)
    with pytest.raises(ClockError):
        s.run_until(1)


def test_context_hash_deterministic():
    def run():
        ctx = SimContext(seed=42)
        ctx.scheduler.schedule(3, "spawn", lambda: ctx.rng.randint(1, 6))
        ctx.scheduler.run_until(10)
        return ctx.state_hash()
    assert run() == run()


def test_scheduler_zero_delay_reentry_and_queue_are_bounded(monkeypatch):
    from skeleton.gameforge.batch_b071 import sim_clock as mod

    monkeypatch.setattr(mod, "MAX_EVENTS_PER_RUN", 5)
    c = SimClock()
    scheduler = EventScheduler(c)
    calls = []

    def requeue():
        calls.append(c.tick)
        scheduler.schedule(0, "again", requeue)

    scheduler.schedule(0, "again", requeue)
    with pytest.raises(ClockError, match="run budget"):
        scheduler.run_until(1)
    assert calls == [0] * 5
    assert scheduler.pending() == 1 and c.tick == 0
    assert len(scheduler.log) == 5

    monkeypatch.setattr(mod, "MAX_QUEUE_EVENTS", 1)
    with pytest.raises(ClockError, match="queue exceeds bound"):
        scheduler.schedule(1, "extra", lambda: None)


def test_clock_and_scheduler_reject_noninteger_or_overflowing_time():
    from skeleton.gameforge.batch_b071.sim_clock import MAX_SIM_TICK

    for bad in (True, 1.5, -1, MAX_SIM_TICK + 1):
        with pytest.raises(ClockError):
            SimClock(start_tick=bad)
        with pytest.raises(ClockError):
            DeterministicRng(bad)
    c = SimClock(start_tick=MAX_SIM_TICK)
    with pytest.raises(ClockError, match="exceeds bound"):
        c.advance(1)
    scheduler = EventScheduler(c)
    with pytest.raises(ClockError, match="exceeds bound"):
        scheduler.schedule(1, "overflow", lambda: None)
    with pytest.raises(ClockError):
        scheduler.run_until(True)
