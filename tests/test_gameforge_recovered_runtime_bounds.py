"""Recovered buffer ownership and coalescing admission regressions."""
import asyncio

import pytest

from skeleton.frontier.gameforge_runtime import BufferClass, BufferPool, RequestCoalescer


def test_reclaimed_storage_never_aliases_a_new_owner():
    pool = BufferPool(class_cap=1)
    first = pool.lease(10)
    first.data[:3] = b"old"
    view = memoryview(first.data)
    assert pool.reclaim(first)
    second = pool.lease(10)
    assert len(second.data) == BufferClass.SMALL.value
    assert not any(second.data)
    view[:3] = b"bad"
    assert not any(second.data)
    assert not pool.reclaim(first)
    assert pool.reclaim(second)
    view.release()


def test_active_and_size_admission_fail_without_allocating():
    pool = BufferPool(class_cap=1, active_cap=1)
    lease = pool.lease(1)
    with pytest.raises(RuntimeError, match="capacity"):
        pool.lease(1)
    with pytest.raises(ValueError, match="largest"):
        pool.lease(BufferClass.LARGE.value + 1)
    assert pool.leased == 1
    assert pool.reclaim(lease)
    assert pool.leased == 0


@pytest.mark.asyncio
async def test_coalescer_rejects_new_keys_under_pressure():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch(key):
        entered.set()
        await release.wait()
        return key

    gate = RequestCoalescer(fetch, max_in_flight=1)
    leader = asyncio.create_task(gate.get("one"))
    await entered.wait()
    follower = asyncio.create_task(gate.get("one"))
    try:
        with pytest.raises(RuntimeError, match="capacity"):
            await gate.get("two")
    finally:
        release.set()
        assert await leader == "one"
        assert await follower == "one"
    assert gate.in_flight == 0


@pytest.mark.asyncio
async def test_leader_cancellation_clears_capacity_and_followers():
    entered = asyncio.Event()

    async def fetch(key):
        entered.set()
        await asyncio.Future()

    gate = RequestCoalescer(fetch, max_in_flight=1)
    leader = asyncio.create_task(gate.get("one"))
    await entered.wait()
    follower = asyncio.create_task(gate.get("one"))
    await asyncio.sleep(0)
    leader.cancel()
    for task in (leader, follower):
        with pytest.raises(asyncio.CancelledError):
            await task
    assert gate.in_flight == 0
