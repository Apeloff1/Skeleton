import pytest

from skeleton.shells.dedupe import DedupeConflict, DedupeRegistry
from skeleton.shells.leases import LeaseConflict, LeaseRegistry
from skeleton.shells.queue import QueueState, ShellWorkQueue
from skeleton.shells.rate_limit import RateLimitPolicy, RateLimiter, TokenBucket
from skeleton.shells.runner import ShellCommand


def test_lease_acquire_conflict_release():
    now = [0.0]
    leases = LeaseRegistry(clock=lambda: now[0])
    first = leases.acquire("python", "worker-a", ttl_seconds=10)
    with pytest.raises(LeaseConflict):
        leases.acquire("python", "worker-b", ttl_seconds=10)
    assert leases.release(first)
    second = leases.acquire("python", "worker-b", ttl_seconds=10)
    assert second.owner == "worker-b"


def test_lease_expiry_allows_reacquire():
    now = [0.0]
    leases = LeaseRegistry(clock=lambda: now[0])
    leases.acquire("python", "a", ttl_seconds=1)
    now[0] = 2
    assert not leases.held("python")
    assert leases.acquire("python", "b").owner == "b"


def test_lease_renew_requires_current_lease():
    now = [0.0]
    leases = LeaseRegistry(clock=lambda: now[0])
    lease = leases.acquire("python", "a", ttl_seconds=1)
    now[0] = 2
    with pytest.raises(LeaseConflict):
        leases.renew(lease)


def test_lease_capacity_is_bounded():
    leases = LeaseRegistry(max_leases=1)
    leases.acquire("a", "worker")
    with pytest.raises(LeaseConflict):
        leases.acquire("b", "worker")


def test_work_queue_priority_and_fifo_tiebreak():
    queue = ShellWorkQueue()
    queue.enqueue(ShellCommand("python", ("later",)), priority=20, item_id="later")
    queue.enqueue(ShellCommand("python", ("first",)), priority=10, item_id="first")
    queue.enqueue(ShellCommand("python", ("second",)), priority=10, item_id="second")
    assert queue.claim("worker").item_id == "first"
    assert queue.claim("worker").item_id == "second"
    assert queue.claim("worker").item_id == "later"


def test_work_queue_complete_requires_current_claim():
    queue = ShellWorkQueue()
    queued = queue.enqueue(ShellCommand("python"), item_id="a")
    with pytest.raises(RuntimeError):
        queue.complete(queued)
    claimed = queue.claim("worker")
    completed = queue.complete(claimed)
    assert completed.state is QueueState.COMPLETED


def test_work_queue_cancel_only_queued():
    queue = ShellWorkQueue()
    queue.enqueue(ShellCommand("python"), item_id="a")
    cancelled = queue.cancel("a")
    assert cancelled.state is QueueState.CANCELLED
    with pytest.raises(RuntimeError):
        queue.cancel("a")


def test_work_queue_capacity_counts_active_only():
    queue = ShellWorkQueue(max_items=1)
    queue.enqueue(ShellCommand("python"), item_id="a")
    with pytest.raises(RuntimeError):
        queue.enqueue(ShellCommand("python"), item_id="b")
    claimed = queue.claim("worker")
    queue.complete(claimed)
    queue.enqueue(ShellCommand("python"), item_id="b")
    assert queue.counts()["queued"] == 1


def test_token_bucket_consumes_and_refills():
    now = [0.0]
    bucket = TokenBucket(RateLimitPolicy(capacity=2, refill_per_second=1), clock=lambda: now[0])
    assert bucket.acquire().allowed
    assert bucket.acquire().allowed
    denied = bucket.acquire()
    assert not denied.allowed
    assert denied.retry_after_seconds == 1
    now[0] = 1
    assert bucket.acquire().allowed


def test_rate_limiter_bounds_key_cardinality():
    limiter = RateLimiter(max_keys=1)
    assert limiter.acquire("a").allowed
    decision = limiter.acquire("b")
    assert not decision.allowed


def test_dedupe_same_key_same_fingerprint_is_idempotent():
    registry = DedupeRegistry()
    first = registry.reserve("k", "f")
    second = registry.reserve("k", "f")
    assert first == second


def test_dedupe_same_key_different_fingerprint_conflicts():
    registry = DedupeRegistry()
    registry.reserve("k", "f1")
    with pytest.raises(DedupeConflict):
        registry.reserve("k", "f2")


def test_dedupe_complete_records_receipt():
    registry = DedupeRegistry()
    registry.reserve("k", "f")
    completed = registry.complete("k", "f", "receipt")
    assert completed.state == "completed"
    assert completed.receipt_id == "receipt"
