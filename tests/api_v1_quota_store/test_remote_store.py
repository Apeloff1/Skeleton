import math

import pytest

from skeleton.api.v1_edge.quota_store import (TAKE_SCRIPT, BucketSpec, CounterStore,
                                              RemoteCounterStore, StoreUnavailable)
from skeleton.api.v1_edge.quota_store.testing import FakeRemoteClient, FlakyCounterStore
from skeleton.api.v1_edge.quota_store import InMemoryCounterStore


def make(now):
    client = FakeRemoteClient()
    return client, RemoteCounterStore(client, clock=lambda: now[0], cooldown_s=5.0)


def test_remote_is_a_counter_store_and_script_shape():
    _, s = make([0.0])
    assert isinstance(s, CounterStore)
    for token in ("HMGET", "HSET", "PEXPIRE", "math.min"):
        assert token in TAKE_SCRIPT


def test_two_replicas_share_one_backend():
    now = [100.0]
    client = FakeRemoteClient()
    a = RemoteCounterStore(client, clock=lambda: now[0])
    b = RemoteCounterStore(client, clock=lambda: now[0])
    spec = BucketSpec(3, 1.0)
    assert a.take("t", spec).allowed
    assert b.take("t", spec).allowed
    assert a.take("t", spec).allowed
    r = b.take("t", spec)
    assert not r.allowed and math.isclose(r.retry_after_s, 1.0)
    assert client.keys() == ["skq:t"]


def test_remote_matches_memory_semantics():
    now = [0.0]
    _, remote = make(now)
    mem = InMemoryCounterStore(clock=lambda: now[0])
    spec = BucketSpec(5, 2.0)
    seq = []
    for step in range(40):
        now[0] = step * 0.3
        cost = 1 + (step % 3)
        r1, r2 = remote.take("k", spec, cost), mem.take("k", spec, cost)
        seq.append(r1.allowed)
        assert r1.allowed == r2.allowed
        assert math.isclose(r1.remaining, r2.remaining, abs_tol=1e-6)
    assert True in seq and False in seq


def test_remote_peek_and_reset():
    now = [0.0]
    client, s = make(now)
    spec = BucketSpec(2, 1.0)
    assert s.peek("k", spec).remaining_int == 2
    s.take("k", spec, 2)
    assert s.peek("k", spec).remaining_int == 0
    s.reset("k")
    assert client.keys() == []
    assert s.healthy()


def test_outage_raises_and_trips_circuit():
    now = [0.0]
    client, s = make(now)
    spec = BucketSpec(2, 1.0)
    client.down = True
    for _ in range(3):
        with pytest.raises(StoreUnavailable):
            s.take("k", spec)
    assert s.circuit_open and not s.healthy()
    calls = len(client.calls)
    with pytest.raises(StoreUnavailable, match="circuit open"):
        s.take("k", spec)
    assert len(client.calls) == calls  # backend not called while open
    client.down = False
    now[0] = 6.0
    assert s.take("k", spec).allowed and not s.circuit_open


def test_timeout_and_corrupt_reply_fail_closed():
    now = [0.0]
    client, s = make(now)
    spec = BucketSpec(2, 1.0)
    client.timeout = True
    with pytest.raises(StoreUnavailable):
        s.take("k", spec)
    with pytest.raises(StoreUnavailable):
        s.peek("k", spec)
    with pytest.raises(StoreUnavailable):
        s.reset("k")
    client.timeout = False
    client.corrupt = True
    now[0] = 10
    with pytest.raises(StoreUnavailable):
        s.take("k", spec)


def test_remote_ttl_expiry_and_bad_args():
    now = [0.0]
    client = FakeRemoteClient(clock=lambda: now[0])
    s = RemoteCounterStore(client, clock=lambda: now[0])
    spec = BucketSpec(2, 1.0)
    s.take("k", spec, 2)
    now[0] = 2.5
    assert client.get_bucket("skq:k") is not None
    s.take("k", spec)
    now[0] = 10
    client._expire("skq:k", now[0] * 1000)
    assert client.keys() == []
    with pytest.raises(ValueError):
        s.take("k", spec, 0)
    with pytest.raises(ValueError):
        RemoteCounterStore(client, trip_after=0)


def test_flaky_wrapper():
    f = FlakyCounterStore(InMemoryCounterStore())
    spec = BucketSpec(1, 1)
    assert f.take("a", spec).allowed and f.healthy()
    f.down = True
    for op in (lambda: f.take("a", spec), lambda: f.peek("a", spec), lambda: f.reset("a")):
        with pytest.raises(StoreUnavailable):
            op()
    assert not f.healthy()


def test_backend_explicit_unavailability_trips_bounded_circuit():
    now = [0.0]

    class UnavailableClient:
        calls = 0
        def eval_take(self, *args):
            self.calls += 1
            raise StoreUnavailable("offline", backend="fake")

    client = UnavailableClient()
    s = RemoteCounterStore(client, clock=lambda: now[0], trip_after=2)
    spec = BucketSpec(2, 1.0)
    for _ in range(2):
        with pytest.raises(StoreUnavailable):
            s.take("key", spec)
    assert s.circuit_open
    with pytest.raises(StoreUnavailable, match="circuit open"):
        s.take("key", spec)
    assert client.calls == 2


def test_remote_clock_rollback_preserves_refill_high_watermark():
    now = [1000.0]
    client = FakeRemoteClient(clock=lambda: now[0])
    s = RemoteCounterStore(client, clock=lambda: now[0])
    spec = BucketSpec(2, 1.0)
    assert s.take("hot", spec, 2).allowed
    now[0] = 0.0
    assert not s.take("hot", spec).allowed
    now[0] = 1000.0
    assert not s.take("hot", spec).allowed
    now[0] = 1001.0
    assert s.take("hot", spec).allowed
    assert "effective_now" in TAKE_SCRIPT
