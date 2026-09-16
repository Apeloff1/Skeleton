from __future__ import annotations

from dataclasses import dataclass

from .models import PlanItem, WorkerState


@dataclass(frozen=True, slots=True)
class DelegationDecision:
    allowed: bool
    reason: str


def may_delegate(*, worker: WorkerState, item: PlanItem, overtime_soft_limit_minutes: int) -> DelegationDecision:
    if worker.status == "offline":
        return DelegationDecision(False, "worker-offline")
    if worker.status == "blocked":
        return DelegationDecision(False, "worker-blocked")
    if worker.team != item.target_team:
        return DelegationDecision(False, "cross-team")
    if worker.overtime_minutes >= overtime_soft_limit_minutes:
        return DelegationDecision(False, "overtime-soft-limit")
    if item.status in {"done", "rejected"}:
        return DelegationDecision(False, "terminal-item")
    return DelegationDecision(True, "allowed")
