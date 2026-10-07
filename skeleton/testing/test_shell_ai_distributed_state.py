"""Distributed AI state CAS, lease, fencing, and backend protocol tests."""

from __future__ import annotations

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    FencedLease,
    InMemoryFencedStore,
    LeaseConflict,
)
from skeleton.shells.ai.store_protocol import (
    DistributedAIBackend,
    FencedLeaseBackend,
    VersionedStateBackend,
)


def test_distributed_store_satisfies_protocols():
    store = InMemoryFencedStore()
    assert isinstance(store, VersionedStateBackend)
    assert isinstance(store, FencedLeaseBackend)
    assert isinstance(store, DistributedAIBackend)


def test_put_if_absent_revision_one():
    store = InMemoryFencedStore()
    record = store.put_if_absent("n", "k", {"x": 1})
    assert record.revision == 1
    assert record.value == {"x": 1}


def test_put_if_absent_conflict():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    with pytest.raises(DistributedStateConflict):
        store.put_if_absent("n", "k", 2)


def test_compare_and_swap_updates_revision():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    updated = store.compare_and_swap(
        "n",
        "k",
        expected_revision=1,
        value=2,
    )
    assert updated.revision == 2
    assert updated.value == 2


def test_compare_and_swap_stale_revision_fails():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    store.compare_and_swap("n", "k", expected_revision=1, value=2)
    with pytest.raises(DistributedStateConflict):
        store.compare_and_swap("n", "k", expected_revision=1, value=3)


def test_compare_and_swap_can_create_with_revision_zero():
    store = InMemoryFencedStore()
    record = store.compare_and_swap(
        "n",
        "k",
        expected_revision=0,
        value="created",
    )
    assert record.revision == 1


def test_compare_and_swap_missing_nonzero_fails():
    store = InMemoryFencedStore()
    with pytest.raises(DistributedStateConflict):
        store.compare_and_swap(
            "n",
            "missing",
            expected_revision=1,
            value="x",
        )


def test_delete_with_expected_revision():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    assert store.delete("n", "k", expected_revision=1)
    assert store.get("n", "k") is None


def test_delete_stale_revision_fails():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    with pytest.raises(DistributedStateConflict):
        store.delete("n", "k", expected_revision=2)


def test_delete_missing_is_false():
    assert not InMemoryFencedStore().delete("n", "k", expected_revision=1)


def test_record_capacity():
    store = InMemoryFencedStore(max_records=1)
    store.put_if_absent("n", "a", 1)
    with pytest.raises(RuntimeError):
        store.put_if_absent("n", "b", 2)


def test_records_sorted_and_filterable():
    store = InMemoryFencedStore()
    store.put_if_absent("z", "b", 1)
    store.put_if_absent("a", "c", 1)
    store.put_if_absent("a", "a", 1)
    assert [(r.namespace, r.key) for r in store.records()] == [
        ("a", "a"),
        ("a", "c"),
        ("z", "b"),
    ]
    assert [r.key for r in store.records("a")] == ["a", "c"]


def test_acquire_lease_token_one():
    now = [0.0]
    store = InMemoryFencedStore(clock=lambda: now[0])
    lease = store.acquire_lease("n", "k", owner="a", ttl_seconds=10)
    assert lease.fencing_token == 1
    assert lease.active(0)
    assert lease.expires_at == 10


def test_second_owner_cannot_acquire_live_lease():
    store = InMemoryFencedStore()
    store.acquire_lease("n", "k", owner="a", ttl_seconds=10)
    with pytest.raises(LeaseConflict):
        store.acquire_lease("n", "k", owner="b", ttl_seconds=10)


def test_same_owner_cannot_duplicate_live_lease():
    store = InMemoryFencedStore()
    store.acquire_lease("n", "k", owner="a", ttl_seconds=10)
    with pytest.raises(LeaseConflict):
        store.acquire_lease("n", "k", owner="a", ttl_seconds=10)


def test_expired_lease_gets_higher_fencing_token():
    now = [0.0]
    store = InMemoryFencedStore(clock=lambda: now[0])
    first = store.acquire_lease("n", "k", owner="a", ttl_seconds=1)
    now[0] = 1
    second = store.acquire_lease("n", "k", owner="b", ttl_seconds=1)
    assert second.fencing_token == first.fencing_token + 1


def test_old_lease_cannot_fence_after_reacquire():
    now = [0.0]
    store = InMemoryFencedStore(clock=lambda: now[0])
    first = store.acquire_lease("n", "k", owner="a", ttl_seconds=1)
    now[0] = 1
    store.acquire_lease("n", "k", owner="b", ttl_seconds=10)
    with pytest.raises(LeaseConflict):
        store.require_fence(first)


def test_renew_preserves_fencing_token():
    now = [0.0]
    store = InMemoryFencedStore(clock=lambda: now[0])
    first = store.acquire_lease("n", "k", owner="a", ttl_seconds=1)
    now[0] = 0.5
    renewed = store.renew_lease(first, ttl_seconds=5)
    assert renewed.fencing_token == first.fencing_token
    assert renewed.expires_at == 5.5


def test_stale_lease_instance_cannot_renew_after_renewal():
    now = [0.0]
    store = InMemoryFencedStore(clock=lambda: now[0])
    first = store.acquire_lease("n", "k", owner="a", ttl_seconds=1)
    renewed = store.renew_lease(first, ttl_seconds=5)
    assert renewed != first
    with pytest.raises(LeaseConflict):
        store.renew_lease(first, ttl_seconds=5)


def test_release_live_lease():
    store = InMemoryFencedStore()
    lease = store.acquire_lease("n", "k", owner="a", ttl_seconds=10)
    assert store.release_lease(lease)
    assert store.leases() == ()


def test_stale_lease_cannot_release_new_owner():
    now = [0.0]
    store = InMemoryFencedStore(clock=lambda: now[0])
    old = store.acquire_lease("n", "k", owner="a", ttl_seconds=1)
    now[0] = 1
    new = store.acquire_lease("n", "k", owner="b", ttl_seconds=10)
    with pytest.raises(LeaseConflict):
        store.release_lease(old)
    store.require_fence(new)


def test_fenced_compare_and_swap_requires_live_lease():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    fake = FencedLease("n", "k", "a", 1, 0, 100)
    with pytest.raises(LeaseConflict):
        store.fenced_compare_and_swap(
            fake,
            expected_revision=1,
            value=2,
        )


def test_fenced_compare_and_swap_updates_record():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    lease = store.acquire_lease("n", "k", owner="a", ttl_seconds=10)
    updated = store.fenced_compare_and_swap(
        lease,
        expected_revision=1,
        value=2,
    )
    assert updated.revision == 2
    assert updated.value == 2


def test_fenced_compare_and_swap_still_enforces_revision():
    store = InMemoryFencedStore()
    store.put_if_absent("n", "k", 1)
    lease = store.acquire_lease("n", "k", owner="a", ttl_seconds=10)
    with pytest.raises(DistributedStateConflict):
        store.fenced_compare_and_swap(
            lease,
            expected_revision=2,
            value=2,
        )


def test_lease_capacity_counts_active_leases():
    store = InMemoryFencedStore(max_leases=1)
    store.acquire_lease("n", "a", owner="a", ttl_seconds=10)
    with pytest.raises(RuntimeError):
        store.acquire_lease("n", "b", owner="b", ttl_seconds=10)


@pytest.mark.parametrize("namespace", ["", "x" * 129])
def test_invalid_namespace(namespace):
    store = InMemoryFencedStore()
    with pytest.raises(ValueError):
        store.get(namespace, "k")


@pytest.mark.parametrize("key", ["", "x" * 513])
def test_invalid_key(key):
    store = InMemoryFencedStore()
    with pytest.raises(ValueError):
        store.get("n", key)


def test_invalid_owner():
    store = InMemoryFencedStore()
    with pytest.raises(ValueError):
        store.acquire_lease("n", "k", owner="", ttl_seconds=1)


def test_invalid_lease_ttl():
    store = InMemoryFencedStore()
    with pytest.raises(ValueError):
        store.acquire_lease("n", "k", owner="a", ttl_seconds=0)
