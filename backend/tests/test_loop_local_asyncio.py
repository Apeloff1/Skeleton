"""Regression tests for event-loop-local admission and cancellation resources."""

from __future__ import annotations

import asyncio

import pytest

from core.loop_local_asyncio import LoopLocalAsyncPrimitive


def test_lock_is_lazy_and_distinct_after_loop_restart() -> None:
    locks = LoopLocalAsyncPrimitive(asyncio.Lock)
    with pytest.raises(RuntimeError, match="no running event loop"):
        locks.get()

    async def lock_for_this_loop():
        lock = locks.get()
        assert locks.get() is lock
        async with lock:
            assert lock.locked()
        return lock

    first = asyncio.run(lock_for_this_loop())
    second = asyncio.run(lock_for_this_loop())
    assert first is not second
    assert not first.locked() and not second.locked()


def test_semaphore_preserves_limit_within_a_running_loop() -> None:
    slots = LoopLocalAsyncPrimitive(lambda: asyncio.Semaphore(1))

    async def check():
        acquired = slots.get()
        assert slots.get() is acquired
        await acquired.acquire()
        try:
            waiter = asyncio.create_task(slots.get().acquire())
            await asyncio.sleep(0)
            assert not waiter.done()
        finally:
            acquired.release()
        assert await asyncio.wait_for(waiter, timeout=1) is True
        acquired.release()
        assert acquired._value == 1
        return acquired

    first = asyncio.run(check())
    second = asyncio.run(check())
    assert first is not second


def test_semaphore_release_after_cancellation_keeps_original_loop_slot() -> None:
    slots = LoopLocalAsyncPrimitive(lambda: asyncio.Semaphore(1))

    async def check():
        acquired = slots.get()
        await acquired.acquire()
        finished = asyncio.Event()

        async def worker():
            try:
                await asyncio.sleep(10)
            finally:
                acquired.release()
                finished.set()

        task = asyncio.create_task(worker())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finished.is_set()
        assert slots.get() is acquired
        assert acquired._value == 1

    asyncio.run(check())
