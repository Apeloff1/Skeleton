import asyncio

import pytest

from skeleton.frontier.gameforge_runtime import BufferClass, BufferPool, RequestCoalescer


def test_buffer_pool_uses_fixed_classes_and_caps_retention() -> None:
    pool = BufferPool(class_cap=2)
    leases = [pool.lease(100), pool.lease(100), pool.lease(100), pool.lease(100)]
    assert all(x.buffer_class is BufferClass.SMALL for x in leases)
    assert pool.leased == 4
    for lease in leases:
        pool.reclaim(lease)
    assert pool.leased == 0
    assert pool.available(BufferClass.SMALL) == 2


def test_buffer_pool_classifies_boundaries() -> None:
    pool = BufferPool()
    assert pool.lease(4096).buffer_class is BufferClass.SMALL
    assert pool.lease(65536).buffer_class is BufferClass.MEDIUM
    assert pool.lease(65537).buffer_class is BufferClass.LARGE


@pytest.mark.asyncio
async def test_coalescer_runs_one_fetch_for_concurrent_same_key() -> None:
    calls = 0

    async def fetch(key: str) -> str:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        return key.upper()

    coalescer = RequestCoalescer(fetch)
    values = await asyncio.gather(*(coalescer.get("alpha") for _ in range(20)))
    assert values == ["ALPHA"] * 20
    assert calls == 1
    assert coalescer.in_flight == 0


@pytest.mark.asyncio
async def test_coalescer_propagates_failure_and_cleans_key() -> None:
    async def fetch(_: str) -> str:
        await asyncio.sleep(0)
        raise RuntimeError("boom")

    coalescer = RequestCoalescer(fetch)
    with pytest.raises(RuntimeError, match="boom"):
        await asyncio.gather(coalescer.get("x"), coalescer.get("x"))
    assert coalescer.in_flight == 0
