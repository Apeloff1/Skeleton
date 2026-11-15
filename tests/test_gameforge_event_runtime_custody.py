"""Focused byte custody, replay identity and cancellation regressions."""
import asyncio
import pytest

from skeleton.frontier.gameforge_event_bus import BoundedEventBus, EventHistoryGap
from skeleton.frontier.gameforge_idempotency import IdempotencyMismatch, IdempotencyWindow
from skeleton.frontier.gameforge_runtime import BufferPool, RequestCoalescer


def test_event_snapshot_and_gap():
    bus = BoundedEventBus(2)
    payload = {"values": [1]}
    event = bus.publish(payload)
    payload["values"].append(2)
    event.value["values"].append(3)
    assert bus.read(0).events[0].value == {"values": [1]}
    bus.publish("second")
    bus.publish("third")
    with pytest.raises(EventHistoryGap):
        bus.read(0)
    assert [event.sequence for event in bus.read(1).events] == [1, 2]
    assert bus.read(3).events == ()


def test_event_byte_retention_and_bad_capacity():
    bus = BoundedEventBus(50, max_bytes=200, max_event_bytes=100)
    for _ in range(10):
        bus.publish("x" * 80)
    assert len(bus) == 2
    assert bus.retained_bytes <= 200
    with pytest.raises(ValueError):
        BoundedEventBus(True)


def test_idempotency_detaches_and_binds_request():
    window = IdempotencyWindow()
    payload = {"result": [1]}
    accepted, returned = window.record("id", payload, fingerprint="a" * 64)
    assert accepted
    payload["result"].append(2)
    returned["result"].append(3)
    assert window.lookup("id", fingerprint="a" * 64) == {"result": [1]}
    with pytest.raises(IdempotencyMismatch):
        window.record("id", {}, fingerprint="b" * 64)


def test_idempotency_aggregate_byte_bound():
    window = IdempotencyWindow(100, max_bytes=256, max_value_bytes=128)
    for index in range(10):
        window.record(str(index), "x" * 100)
    assert len(window) == 2
    assert window.retained_bytes <= 256
    assert window.stats().evicted == 8


def test_buffer_pool_bytes_and_idle_eviction():
    pool = BufferPool(max_bytes=1 << 20)
    small = pool.lease(1)
    with pytest.raises(RuntimeError, match="byte budget"):
        pool.lease(1 << 20)
    assert pool.reclaim(small)
    large = pool.lease(1 << 20)
    assert pool.allocated_bytes == 1 << 20
    assert pool.reclaim(large)
    assert pool.leased == 0


@pytest.mark.asyncio
async def test_coalescer_cancelled_leader_does_not_cancel_follower():
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def fetch(key):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return key

    coalescer = RequestCoalescer(fetch, max_waiters=2)
    first = asyncio.create_task(coalescer.get("x"))
    await entered.wait()
    follower = asyncio.create_task(coalescer.get("x"))
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="waiter"):
        await coalescer.get("x")
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    assert await follower == "x"
    assert calls == 1 and coalescer.in_flight == 0
    await coalescer.aclose()
    with pytest.raises(RuntimeError):
        await coalescer.get("x")
