"""Maintenance policy for evicting stale workers and safely requeuing leases."""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.agents.swarm_runtime import SwarmRuntime

@dataclass(frozen=True, slots=True)
class JanitorResult:
    stale_workers: tuple[str, ...]
    released_leases: int


def reap_stale_workers(runtime: SwarmRuntime, *, stale_after: float, requeue: bool = True, limit: int = 1000) -> JanitorResult:
    if stale_after <= 0: raise ValueError("stale_after must be positive")
    if limit < 1: raise ValueError("limit must be positive")
    stale = tuple(worker.id for worker in runtime.stale_workers(stale_after=stale_after))[:limit]
    released = 0
    for worker_id in stale:
        released += runtime.unregister_worker(worker_id, requeue=requeue)
    return JanitorResult(stale, released)
