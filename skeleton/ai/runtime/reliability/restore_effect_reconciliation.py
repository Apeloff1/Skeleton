"""Fail-closed restore fence for external side effects (G193)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from skeleton.skills.tool_contract import ToolExecutionRequest, ToolExecutionStatus
from skeleton.skills.tool_effect_reconciliation import ReconciliableToolReceiptStore, ToolEffectReconciliationEvidence, ToolEffectReconciliationError

class RestoreEffectFenceError(RuntimeError):
    """Restored external-effect state is unsafe for replay."""

@dataclass(frozen=True, slots=True)
class RestoredEffect:
    request: ToolExecutionRequest
    evidence: ToolEffectReconciliationEvidence | None = None

@dataclass(frozen=True, slots=True)
class RestoreEffectReport:
    reconciled: tuple[str, ...]
    blocked: tuple[str, ...]
    safe_to_resume: bool

def reconcile_restored_effects(store: ReconciliableToolReceiptStore, effects: Iterable[RestoredEffect]) -> RestoreEffectReport:
    """Reconcile restored reservations without invoking a tool handler."""
    if not isinstance(store, ReconciliableToolReceiptStore):
        raise TypeError("store must be ReconciliableToolReceiptStore")
    reconciled: list[str] = []
    blocked: list[str] = []
    seen: set[str] = set()
    for item in effects:
        if not isinstance(item, RestoredEffect):
            raise TypeError("effects must contain RestoredEffect values")
        request = item.request
        identity = request.request_id
        if identity in seen:
            raise RestoreEffectFenceError("duplicate restored request identity")
        seen.add(identity)
        reservation = store.get(tenant_id=request.tenant_id, operation_id=request.operation_id, idempotency_key=request.idempotency_key)
        if reservation is None:
            blocked.append(identity)
            continue
        if reservation.receipt is not None:
            if reservation.receipt.request_id != request.request_id:
                raise RestoreEffectFenceError("terminal restored receipt does not match request identity")
            reconciled.append(identity)
            continue
        if item.evidence is None:
            blocked.append(identity)
            continue
        try:
            receipt = store.reconcile_pending(request, item.evidence)
        except ToolEffectReconciliationError as exc:
            raise RestoreEffectFenceError(f"restored effect reconciliation failed: {identity}") from exc
        if receipt.status not in {ToolExecutionStatus.SUCCEEDED, ToolExecutionStatus.FAILED}:
            raise RestoreEffectFenceError("reconciliation did not produce terminal receipt")
        reconciled.append(identity)
    return RestoreEffectReport(tuple(reconciled), tuple(blocked), not blocked)

def assert_restore_effects_safe(report: RestoreEffectReport) -> None:
    if not isinstance(report, RestoreEffectReport):
        raise TypeError("report must be RestoreEffectReport")
    if not report.safe_to_resume:
        raise RestoreEffectFenceError("restored external effects remain in doubt: " + ",".join(report.blocked))
