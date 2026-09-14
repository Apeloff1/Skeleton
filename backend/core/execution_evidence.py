"""Evidence-derived lifecycle projection for governed product operations.

The control plane deliberately avoids a mutable status column. Lifecycle is
reconstructed from durable queue intent, immutable execution receipts and the
verified WORM audit chain. This makes status explainable, restart-safe and
resistant to stale/inconsistent flags.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class LifecycleEvidence:
    operation_id: str
    state: str
    pending: bool
    executor_bound: bool
    receipt_present: bool
    executed_audit_present: bool
    failed_audit_count: int
    deferred_audit_count: int
    audit_sequences: tuple[int, ...]
    confidence: str


_TERMINAL_AUDIT_KINDS = {"operation_executed"}
_FAILED_KIND = "operation_execution_failed"
_DEFERRED_KIND = "operation_execution_deferred"


def _operation_id_from_detail(detail: str) -> str | None:
    # Audit detail is canonical JSON for product operations. Keep this parser
    # dependency-free and fail closed on malformed historical entries.
    import json

    try:
        raw = json.loads(detail)
    except (TypeError, json.JSONDecodeError):
        return None
    value = raw.get("operation_id") if isinstance(raw, dict) else None
    return str(value) if value else None


def derive_lifecycle(
    operation_id: str,
    *,
    pending_operations: Iterable[dict[str, Any]],
    receipts: Iterable[dict[str, Any]],
    audit_entries: Iterable[dict[str, Any]],
) -> LifecycleEvidence:
    operation_id = operation_id.strip()
    if not operation_id:
        raise ValueError("operation_id is required")

    pending = next((item for item in pending_operations if str(item.get("operation_id")) == operation_id), None)
    receipt = next((item for item in receipts if str(item.get("operation_id")) == operation_id), None)

    relevant: list[dict[str, Any]] = []
    for entry in audit_entries:
        if _operation_id_from_detail(str(entry.get("detail", ""))) == operation_id:
            relevant.append(entry)
    relevant.sort(key=lambda item: int(item.get("seq", 0)))

    kinds = [str(item.get("kind", "")) for item in relevant]
    executed = any(kind in _TERMINAL_AUDIT_KINDS for kind in kinds)
    failed = sum(kind == _FAILED_KIND for kind in kinds)
    deferred = sum(kind == _DEFERRED_KIND for kind in kinds)
    receipt_present = receipt is not None
    pending_present = pending is not None
    bound = bool(pending.get("executor_bound")) if pending is not None else False

    # Evidence precedence is intentional. A receipt proves an executor produced a
    # concrete result. Queue presence proves confirmation has not removed intent.
    # Executed audit without a receipt is suspicious for native receipt-writing
    # executors and is therefore surfaced as an evidence gap, not "confirmed".
    if receipt_present and not pending_present and executed:
        state, confidence = "confirmed", "high"
    elif receipt_present and pending_present:
        state, confidence = "executed_unconfirmed", "high"
    elif executed and not receipt_present:
        state, confidence = "evidence_gap", "low"
    elif pending_present and bound:
        state, confidence = "pending_bound", "high"
    elif pending_present:
        state, confidence = "pending_unbound", "high"
    elif failed:
        state, confidence = "failed_not_pending", "medium"
    else:
        state, confidence = "unknown", "low"

    return LifecycleEvidence(
        operation_id=operation_id,
        state=state,
        pending=pending_present,
        executor_bound=bound,
        receipt_present=receipt_present,
        executed_audit_present=executed,
        failed_audit_count=failed,
        deferred_audit_count=deferred,
        audit_sequences=tuple(int(item.get("seq", 0)) for item in relevant),
        confidence=confidence,
    )


def derive_ledger(
    *,
    pending_operations: Iterable[dict[str, Any]],
    receipts: Iterable[dict[str, Any]],
    audit_entries: Iterable[dict[str, Any]],
) -> tuple[LifecycleEvidence, ...]:
    pending_list = list(pending_operations)
    receipt_list = list(receipts)
    audit_list = list(audit_entries)
    ids = {str(item.get("operation_id")) for item in pending_list if item.get("operation_id")}
    ids.update(str(item.get("operation_id")) for item in receipt_list if item.get("operation_id"))
    for entry in audit_list:
        operation_id = _operation_id_from_detail(str(entry.get("detail", "")))
        if operation_id:
            ids.add(operation_id)
    return tuple(
        derive_lifecycle(
            operation_id,
            pending_operations=pending_list,
            receipts=receipt_list,
            audit_entries=audit_list,
        )
        for operation_id in sorted(ids)
    )
