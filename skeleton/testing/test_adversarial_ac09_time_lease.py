from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Lease:
    owner: str
    expires_at: int
    generation: int


def valid(lease: Lease, now: int, owner: str, generation: int) -> bool:
    return lease.owner == owner and lease.generation == generation and now < lease.expires_at


def test_clock_skew_does_not_extend_expired_lease():
    lease = Lease("worker-a", 100, 7)
    assert not valid(lease, 101, "worker-a", 7)


def test_expiry_fences_stale_worker():
    lease = Lease("worker-a", 100, 7)
    assert not valid(lease, 100, "worker-a", 7)
    assert valid(Lease("worker-b", 200, 8), 150, "worker-b", 8)


def test_generation_fencing_blocks_old_owner():
    lease = Lease("worker-b", 200, 8)
    assert not valid(lease, 150, "worker-b", 7)
