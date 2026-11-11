import math
import threading

import pytest

from skeleton.api.v1_edge.quota_store import (BucketSpec, CounterStore, InMemoryCounterStore,
                                              compute_take)


def test_compute_take_starts_full_and_refills():
    spec = BucketSpec(3, 1.0)
    r, lvl = compute_take(None, None, spec, 1, 10.0)
    assert r.allowed and lvl == 2 and r.retry_after_s == 0
    r, lvl = compute_take(0.0, 10.0, spec, 1, 10.5)
    assert not r.allowed and math.isclose(r.retry_after_s, 0.5)
    r, lvl = compute_take(0.0, 10.0, spec, 1, 100.0)
    assert r.allowed and lvl == 2  # capped at capacity


def test_compute_take_rejects_bad_cost_and_never_negative_refill():
    spec = BucketSpec(2, 1.0)
    with pytest.raises(ValueError):
        compute_take(None, None, spec, 0, 0)
    with pytest.raises(ValueError):
        compute_take(None, None, spec, float("nan"), 0)
    r, lvl = compute_take(1.0, 50.0, spec, 1, 10.0)  # clock went backwards
    assert r.allowed and lvl == 0


def test_cost_above_capacity_never_spends():
    spec = BucketSpec(2, 1.0)
    r, lvl = compute_take(None, None, spec, 5, 0)
    assert not r.allowed and math.isinf(r.retry_after_s) and lvl == 2


def test_bucket_spec_validation():
    with pytest.raises(ValueError):
        BucketSpec(0, 1)
    with pytest.raises(ValueError):
        BucketSpec(1, 0)
    with pytest.raises(ValueError):
        BucketSpec(float("inf"), 1)
    assert BucketSpec(10, 2).full_after_s == 5


def test_memory_store_is_a_counter_store():
    assert isinstance(InMemoryCounterStore(), CounterStore)


def test_memory_take_peek_reset():
    now = [0.0]
    s = InMemoryCounterStore(clock=lambda: now[0])
    spec = BucketSpec(2, 1.0)
    assert s.take("k", spec).allowed
    assert s.take("k", spec).allowed
    r = s.take("k", spec)
    assert not r.allowed and r.remaining_int == 0
    assert not s.peek("k", spec).allowed
    now[0] = 1.0
    assert s.peek("k", spec).remaining_int == 1
    s.reset("k")
    assert s.peek("k", spec).remaining_int == 2
    assert s.healthy()


def test_memory_expiry_equals_full_bucket():
    now = [0.0]
    s = InMemoryCounterStore(clock=lambda: now[0])
    spec = BucketSpec(4, 2.0)  # full after 2s
    s.take("k", spec, 4)
    assert len(s) == 1
    now[0] = 2.0
    r = s.take("k", spec)
    assert r.allowed and math.isclose(r.remaining, 3)


def test_memory_lru_bound():
    s = InMemoryCounterStore(max_keys=5, clock=lambda: 0.0)
    spec = BucketSpec(1, 0.001)
    for i in range(12):
        s.take(f"k{i}", spec)
    assert len(s) == 5 and s.evictions == 7
    with pytest.raises(ValueError):
        InMemoryCounterStore(max_keys=0)


def test_memory_is_atomic_under_threads():
    s = InMemoryCounterStore(clock=lambda: 0.0)
    spec = BucketSpec(100, 0.0001)
    allowed = []
    lock = threading.Lock()

    def worker():
        for _ in range(50):
            if s.take("hot", spec).allowed:
                with lock:
                    allowed.append(1)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(allowed) == 100
