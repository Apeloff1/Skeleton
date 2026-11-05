"""Capacity and concurrency fences for tenant-bound edge idempotency."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from skeleton.api.v1_edge.envelope import EdgeError
from skeleton.api.v1_edge.idempotency import IdempotencyCache


def test_live_inflight_entry_is_never_evicted_at_capacity():
    now = [100.0]
    cache = IdempotencyCache(max_entries=1, clock=lambda: now[0])
    assert cache.begin("tenant-a:one", "fp") is None
    with pytest.raises(EdgeError) as exc:
        cache.begin("tenant-a:two", "fp2")
    assert exc.value.status == 503 and exc.value.code == "EDGE.IDEMPOTENCY.CAPACITY"
    with pytest.raises(EdgeError) as replay:
        cache.begin("tenant-a:one", "fp")
    assert replay.value.status == 409 and replay.value.code == "EDGE.IDEMPOTENCY.IN_FLIGHT"


def test_completed_response_remains_replayable_until_ttl():
    now = [100.0]
    cache = IdempotencyCache(ttl_s=10, max_entries=1, clock=lambda: now[0])
    cache.begin("tenant-a:one", "fp")
    cache.complete("tenant-a:one", 201, [(b"content-type", b"application/json")], b"ok")
    with pytest.raises(EdgeError) as exc:
        cache.begin("tenant-a:two", "fp2")
    assert exc.value.status == 503
    stored = cache.begin("tenant-a:one", "fp")
    assert stored is not None and stored.done and stored.body == b"ok"
    now[0] = 111.0
    assert cache.begin("tenant-a:two", "fp2") is None


def test_capacity_is_released_after_abandon_or_server_failure():
    cache = IdempotencyCache(max_entries=1)
    cache.begin("one", "fp")
    cache.abandon("one")
    assert cache.begin("two", "fp2") is None
    cache.complete("two", 500, [], b"failed")
    assert cache.begin("three", "fp3") is None


def test_atomic_begin_has_exactly_one_winner():
    cache = IdempotencyCache(max_entries=1)
    barrier = Barrier(2)

    def attempt():
        barrier.wait()
        try:
            cache.begin("same", "fp")
            return "winner"
        except EdgeError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted((a, b)) == ["EDGE.IDEMPOTENCY.IN_FLIGHT", "winner"]


@pytest.mark.parametrize("kwargs", [
    {"max_entries": 0}, {"max_entries": True}, {"max_body": 0},
    {"ttl_s": 0}, {"ttl_s": float("nan")}, {"ttl_s": float("inf")},
])
def test_invalid_capacity_configuration_rejected(kwargs):
    with pytest.raises(ValueError):
        IdempotencyCache(**kwargs)
