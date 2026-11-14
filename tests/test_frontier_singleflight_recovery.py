"""Source-recovered idempotency and waiter custody."""
import asyncio

import pytest

from skeleton.frontier.singleflight import IdempotencyConflict, SingleFlight


@pytest.mark.asyncio
async def test_shared_waiter_and_cached_result_are_isolated():
    gate = SingleFlight()
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def work():
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return {"items": [1]}

    first = asyncio.create_task(gate.run("key", "same", work))
    await entered.wait()
    second = asyncio.create_task(gate.run("key", "same", work))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    result = await second
    result["items"].append(2)
    assert await gate.run("key", "same", work) == {"items": [1]}
    assert calls == 1
    with pytest.raises(IdempotencyConflict):
        await gate.run("key", "different", work)


@pytest.mark.asyncio
async def test_large_result_is_never_cached():
    gate = SingleFlight()

    async def work():
        return "x" * 262145

    with pytest.raises(ValueError):
        await gate.run("one", "same", work)
    assert gate.stats()["cached"] == gate.stats()["inflight"] == 0
