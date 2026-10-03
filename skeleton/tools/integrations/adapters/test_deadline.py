"""Tests for clocks, deadlines, cancellation and run_with_deadline."""

from __future__ import annotations

import asyncio
import math

import pytest

from .deadline import CancellationToken, Deadline, ManualClock, MonotonicClock, run_with_deadline
from .errors import DeadlineExceededError, OperationCancelledError


def test_manual_clock_sleep_advances_and_records():
    clock = ManualClock(10.0)
    asyncio.run(clock.sleep(2.5))
    assert clock.now() == 12.5
    assert clock.sleeps == [2.5]
    with pytest.raises(ValueError):
        clock.advance(-1)


def test_deadline_remaining_expired_and_cap():
    clock = ManualClock()
    dl = Deadline.after(5, clock)
    assert dl.remaining() == 5
    assert dl.cap(10) == 5
    assert dl.cap(2) == 2
    assert dl.cap(None) == 5
    clock.advance(5)
    assert dl.expired()
    with pytest.raises(DeadlineExceededError):
        dl.check("thing")


def test_unbounded_deadline():
    dl = Deadline.never(ManualClock())
    assert dl.unbounded and math.isinf(dl.remaining())
    assert dl.cap(None) is None
    assert dl.cap(3) == 3
    assert not dl.expired()
    assert Deadline.after(None).unbounded


def test_deadline_tighten_never_loosens():
    clock = ManualClock()
    dl = Deadline.after(10, clock)
    assert dl.tighten(3).remaining() == 3
    assert dl.tighten(30).remaining() == 10
    assert dl.tighten(None) is dl
    with pytest.raises(ValueError):
        Deadline.after(-1, clock)


def test_cancellation_token_callbacks_and_children():
    seen: list[str] = []
    parent = CancellationToken()
    child = parent.child()
    child.on_cancel(seen.append)
    parent.on_cancel(lambda _r: (_ for _ in ()).throw(RuntimeError("bad callback")))
    parent.cancel("shutdown")
    assert parent.cancelled and child.cancelled
    assert child.reason == "shutdown"
    assert seen == ["shutdown"]
    late: list[str] = []
    child.on_cancel(late.append)
    assert late == ["shutdown"]
    parent.cancel("again")
    assert parent.reason == "shutdown"
    with pytest.raises(OperationCancelledError):
        child.check()


def test_run_with_deadline_returns_result():
    async def work() -> int:
        await asyncio.sleep(0)
        return 7

    assert asyncio.run(run_with_deadline(work, timeout=1.0)) == 7


def test_run_with_deadline_times_out_and_cancels_inner():
    state = {"cancelled": False}

    async def slow() -> None:
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    with pytest.raises(DeadlineExceededError):
        asyncio.run(run_with_deadline(slow, timeout=0.02, what="slow op"))
    assert state["cancelled"]


def test_run_with_deadline_honours_token():
    async def main() -> None:
        token = CancellationToken()

        async def slow() -> None:
            await asyncio.sleep(5)

        loop = asyncio.get_running_loop()
        loop.call_later(0.02, token.cancel, "user abort")
        await run_with_deadline(slow, timeout=2.0, token=token)

    with pytest.raises(OperationCancelledError, match="user abort"):
        asyncio.run(main())


def test_run_with_deadline_fails_fast_when_already_expired_or_cancelled():
    clock = ManualClock()
    dl = Deadline.after(1, clock)
    clock.advance(2)

    async def never() -> None:  # pragma: no cover - must not run
        raise AssertionError("should not run")

    with pytest.raises(DeadlineExceededError):
        asyncio.run(run_with_deadline(never, deadline=dl))
    token = CancellationToken()
    token.cancel()
    with pytest.raises(OperationCancelledError):
        asyncio.run(run_with_deadline(never, token=token))


def test_run_with_deadline_propagates_inner_exception():
    async def boom() -> None:
        raise KeyError("x")

    with pytest.raises(KeyError):
        asyncio.run(run_with_deadline(boom, timeout=1.0))


def test_monotonic_clock_sleep_zero():
    clock = MonotonicClock()
    before = clock.now()
    asyncio.run(clock.sleep(0))
    assert clock.now() >= before
