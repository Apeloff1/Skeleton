import asyncio
import random
import threading
import time

import pytest

from skeleton.gate_plane.core_mount import DispatchScheduler


def run(coro):
    return asyncio.run(coro)


def test_validation():
    for kw in ({"interval": 0}, {"jitter": 1.0}, {"limit": 0}):
        with pytest.raises(ValueError):
            DispatchScheduler(dispatch=lambda n: None, **kw)


def test_jitter_bounds_and_backoff():
    s = DispatchScheduler(dispatch=lambda n: None, interval=10, jitter=0.2, rng=random.Random(1))
    ds = [s.next_delay() for _ in range(200)]
    assert min(ds) >= 8 and max(ds) <= 12 and len(set(ds)) > 1
    s.stats.consecutive_errors = 3
    s.jitter = 0
    assert s.next_delay() == 60.0  # capped at max_backoff
    s.stats.consecutive_errors = 1
    assert s.next_delay() == 20.0


def test_tick_passes_limit_and_records_report():
    seen = []
    s = DispatchScheduler(dispatch=lambda n: seen.append(n) or "rep", limit=7)
    assert run(s.tick()) is True
    assert seen == [7] and s.stats.last_report == "rep" and s.stats.ticks == 1


def test_error_isolation_and_recovery():
    calls = {"n": 0}

    def flaky(n):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("db down")
        return "ok"

    s = DispatchScheduler(dispatch=flaky)

    async def go():
        await s.tick()
        assert s.stats.errors == 1 and s.stats.consecutive_errors == 1
        assert "db down" in s.stats.last_error
        await s.tick()

    run(go())
    assert s.stats.consecutive_errors == 0 and s.stats.last_report == "ok"


def test_single_flight():
    gate = threading.Event()
    active = {"max": 0, "now": 0}

    def slow(n):
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        gate.wait(2)
        active["now"] -= 1

    s = DispatchScheduler(dispatch=slow)

    async def go():
        t1 = asyncio.create_task(s.tick())
        await asyncio.sleep(0.05)
        assert await s.tick() is False
        gate.set()
        assert await t1 is True

    run(go())
    assert active["max"] == 1 and s.stats.skipped_overlap == 1


def test_loop_runs_and_stops_cleanly():
    count = {"n": 0}
    s = DispatchScheduler(dispatch=lambda n: count.__setitem__("n", count["n"] + 1),
                          interval=0.01, jitter=0.0)

    async def go():
        s.start()
        s.start()  # idempotent
        await asyncio.sleep(0.1)
        await s.stop()
        assert not s.running
        n = count["n"]
        await asyncio.sleep(0.05)
        return n

    n = run(go())
    assert n >= 3 and count["n"] == n


def test_stop_waits_for_inflight_tick():
    done = []

    def slow(n):
        time.sleep(0.2)
        done.append(1)

    s = DispatchScheduler(dispatch=slow, interval=10)

    async def go():
        s.start()
        await asyncio.sleep(0.05)
        await s.stop()

    run(go())
    assert done == [1]


def test_stop_times_out_without_hanging():
    s = DispatchScheduler(dispatch=lambda n: time.sleep(0.5), interval=10, shutdown_timeout=0.05)

    async def go():
        s.start()
        await asyncio.sleep(0.02)
        t0 = time.monotonic()
        await s.stop()
        return time.monotonic() - t0

    assert run(go()) < 0.4
