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
