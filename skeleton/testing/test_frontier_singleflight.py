import asyncio

import pytest

from skeleton.frontier.singleflight import IdempotencyConflict, SingleFlight
from skeleton.testing.test_frontier_runtime_limits import BlockingAgent, runtime


@pytest.mark.asyncio
async def test_duplicate_requests_share_work_and_results_are_detached():
    agent = BlockingAgent()
    instance = runtime(agent)
    first = asyncio.create_task(instance.execute(agent.name, "same", context={"x": []}, idempotency_key="key"))
    await agent.started.wait()
    second = asyncio.create_task(instance.execute(agent.name, "same", context={"x": []}, idempotency_key="key"))
    await asyncio.sleep(0)
    agent.release.set()
    a, b = await asyncio.gather(first, second)
    assert agent.calls == 1 and a.request_id == b.request_id
    a.output["x"].append(1)
    c = await instance.execute(agent.name, "same", context={"x": []}, idempotency_key="key")
    assert b.output == c.output == {"x": []}
    with pytest.raises(IdempotencyConflict):
        await instance.execute(agent.name, "different", idempotency_key="key")


@pytest.mark.asyncio
async def test_cancelling_one_waiter_preserves_shared_work():
    agent = BlockingAgent()
    instance = runtime(agent)
    first = asyncio.create_task(instance.execute(agent.name, "same", idempotency_key="key"))
    await agent.started.wait()
    second = asyncio.create_task(instance.execute(agent.name, "same", idempotency_key="key"))
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    agent.release.set()
    assert (await second).succeeded
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_last_waiter_cancellation_releases_capacity_and_allows_retry():
    agent = BlockingAgent()
    instance = runtime(agent)
    pending = asyncio.create_task(instance.execute(agent.name, "same", idempotency_key="key"))
    await agent.started.wait()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert instance.stats()["active"] == 0
    assert instance.stats()["idempotency"]["inflight"] == 0
    agent.release.set()
    assert (await instance.execute(agent.name, "same", idempotency_key="key")).succeeded
    assert agent.calls == 2


@pytest.mark.asyncio
async def test_cache_capacity_ttl_and_failed_results():
    now = [0]
    cache = SingleFlight(capacity=1, ttl=1, clock=lambda: now[0])
    calls = []

    async def generate():
        calls.append(1)
        return len(calls)

    assert await cache.run("a", "fingerprint", generate) == 1
    assert await cache.run("a", "fingerprint", generate) == 1
    now[0] = 1
    assert await cache.run("a", "new", generate) == 2
    await cache.run("b", "fp", generate)
    assert cache.stats()["cached"] == 1
    assert await cache.run("a", "new", generate, cacheable=lambda _: False) == 4
    assert await cache.run("a", "new", generate) == 5
