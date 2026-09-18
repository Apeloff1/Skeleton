from __future__ import annotations

from dataclasses import dataclass

from .models import PlanItem, WorkerState


@dataclass(frozen=True, slots=True)
class DelegationDecision:
    allowed: bool
    reason: str


def overtime_exceeds_soft_limit(
    overtime_minutes: int,
    overtime_soft_limit_minutes: int,
) -> bool:
    """Return True when a worker is at or past the overtime soft limit.

    A limit of ``0`` forbids any overtime but still admits a worker with
    zero overtime minutes. Negative inputs fail closed to the same rule
    after being clamped, matching the queue and squad claim surfaces.
    """
    minutes = max(0, int(overtime_minutes))
    limit = max(0, int(overtime_soft_limit_minutes))
    return minutes > 0 if limit == 0 else minutes >= limit


def may_admit_worker(
    *,
    worker: WorkerState,
    overtime_soft_limit_minutes: int,
) -> DelegationDecision:
    """Preemptive fail-closed gate for new work, independent of a plan item.

    Blocked, offline, occupied, and overtime workers must be refused before
    the queue inspects eligible tasks. ``working`` without a current task is
    also refused so a stale heartbeat cannot skip the idle admission path.
    """
    if worker.status == "offline":
        return DelegationDecision(False, "worker-offline")
    if worker.status == "blocked":
        return DelegationDecision(False, "worker-blocked")
    if worker.status == "working":
        return DelegationDecision(False, "worker-working")
    if worker.status != "idle":
        return DelegationDecision(False, "worker-inadmissible")
    if worker.current_task_id is not None:
        return DelegationDecision(False, "worker-occupied")
    if overtime_exceeds_soft_limit(worker.overtime_minutes, overtime_soft_limit_minutes):
        return DelegationDecision(False, "overtime-soft-limit")
    return DelegationDecision(True, "allowed")


def may_delegate(
    *,
    worker: WorkerState,
    item: PlanItem,
    overtime_soft_limit_minutes: int,
) -> DelegationDecision:
    admission = may_admit_worker(
        worker=worker,
        overtime_soft_limit_minutes=overtime_soft_limit_minutes,
    )
    if not admission.allowed:
        return admission
    if worker.team != item.target_team:
        return DelegationDecision(False, "cross-team")
    if item.status in {"done", "rejected"}:
        return DelegationDecision(False, "terminal-item")
    return DelegationDecision(True, "allowed")
