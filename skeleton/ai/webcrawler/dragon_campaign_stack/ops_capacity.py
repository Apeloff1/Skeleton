"""Adaptive, bounded host-slice capacity envelope using measured telemetry.

This narrows an existing request grant, never broadens it. Invalid or stale
external telemetry is a hold rather than an excuse to execute unmetered work.
A zero-sample envelope is safe and diagnostic for the owner's read-only UI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .budget import BudgetProjection
from .contracts import CampaignMandate, digest, finite
from .pressure import ResourceObservation, PressureDecision, recommend_crawl_pressure
from .ops_host_governor import HostGovernor
from .ops_recovery import RecoveryHandshake


@dataclass(frozen=True)
class CapacityEnvelope:
    mandate_digest: str
    governor_digest: str
    recovery_digest: str
    pressure_digest: str | None
    samples_observed: int
    p99_latency_ms: float | None
    available_memory_bytes: int | None
    free_disk_bytes: int | None
    cpu_pressure: float | None
    suggested_parallel_workers: int
    suggested_slice_steps: int
    request_slots_remaining: int
    conservative_byte_capacity: int
    holds: tuple[str, ...]
    envelope_digest: str
    live_worker_capacity_certified: bool = False
    new_budget_granted: bool = False


def recommend_ops_capacity(
    mandate: CampaignMandate, budget: BudgetProjection,
    governor: HostGovernor, recovery: RecoveryHandshake,
    *, now: float, authorized: bool,
    observations: Iterable[ResourceObservation] = (),
) -> tuple[CapacityEnvelope, PressureDecision | None]:
    mandate.admit(now=now, authorized=authorized)
    finite(now, "capacity sample clock")
    if not isinstance(budget, BudgetProjection):
        raise TypeError("canonical crawl budget required")
    if not isinstance(governor, HostGovernor) or not isinstance(recovery, RecoveryHandshake):
        raise TypeError("canonical host and restart receipts required")
    if (governor.mandate_digest != mandate.fingerprint
            or recovery.mandate_digest != mandate.fingerprint
            or governor.source_snapshot_digest != recovery.source_snapshot_digest):
        raise PermissionError("operational capacity receipts from different snapshots")
    rows = tuple(observations)
    if len(rows) > 32:
        raise ValueError("resource sample window too large")
    pressure = None
    holds = list(budget.blockers)
    if not rows:
        holds.append("no_measured_resource_telemetry")
    else:
        pressure = recommend_crawl_pressure(
            mandate, budget, rows, now=now, authorized=authorized,
            max_observations=32,
        )
        holds.extend(pressure.reasons)
    if recovery.held_reasons:
        holds.extend(recovery.held_reasons)
    if not governor.origins:
        holds.append("canonical_frontier_empty")
    if governor.hosts_with_review_holds:
        holds.append("live_robots_and_origin_recheck_required")
    # This envelope is a source advisory; even complete caller witnesses
    # cannot authenticate actual worker/lease/Mongo authority.
    steps = (
        0 if pressure is None or pressure.recommend_pause else
        min(4, pressure.recommend_max_slice_steps,
            pressure.recommend_max_parallel_workers,
            budget.requests_remaining, budget.documents_remaining)
    )
    workers = (
        0 if pressure is None or pressure.recommend_pause else
        min(4, pressure.recommend_max_parallel_workers)
    )
    if recovery.held_reasons:
        steps = workers = 0
    if budget.bytes_remaining < mandate.request.max_response_bytes:
        # A robots probe can use a smaller cap, but capacity cannot claim
        # a full-page work slot when its worst-case reserve is unavailable.
        holds.append("full_response_byte_reserve_not_available")
        steps = workers = 0
    sample = rows[-1] if rows else None
    payload = {
        "mandate": mandate.fingerprint,
        "governor": governor.governor_digest,
        "recovery": recovery.handshake_digest,
        "pressure": pressure.decision_digest if pressure else None,
        "samples": [asdict(x) for x in rows],
        "steps": steps, "workers": workers,
        "remaining_requests": budget.requests_remaining,
        "remaining_bytes": budget.bytes_remaining,
        "holds": sorted(set(holds)),
    }
    return CapacityEnvelope(
        mandate.fingerprint, governor.governor_digest,
        recovery.handshake_digest,
        pressure.decision_digest if pressure else None, len(rows),
        sample.observed_p99_latency_ms if sample else None,
        sample.memory_available_bytes if sample else None,
        sample.disk_free_bytes if sample else None,
        sample.cpu_pressure if sample else None,
        workers, steps, budget.requests_remaining,
        budget.bytes_remaining, tuple(sorted(set(holds))), digest(payload),
    ), pressure
