"""Evidence-derived lifecycle projection for governed product operations.

Lifecycle is reconstructed from durable queue intent, immutable receipts and the
verified WORM audit chain. Every projection carries a deterministic evidence
digest plus explicit anomaly codes, making state explainable and comparable
across restarts without trusting mutable status flags.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class LifecycleEvidence:
    operation_id: str
    state: str
    pending: bool
    executor_bound: bool
    receipt_present: bool
    admitted_audit_present: bool
    executed_audit_present: bool
    executed_audit_count: int
    failed_audit_count: int
    deferred_audit_count: int
    audit_sequences: tuple[int, ...]
    anomalies: tuple[str, ...]
    confidence: str
    evidence_sha256: str


_TERMINAL_AUDIT_KINDS = {"operation_executed"}
_ADMITTED_KIND = "operation_admitted"
_FAILED_KIND = "operation_execution_failed"
_DEFERRED_KIND = "operation_execution_deferred"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _operation_id_from_detail(detail: str) -> str | None:
    try:
        raw = json.loads(detail)
    except (TypeError, json.JSONDecodeError):
        return None
    value = raw.get("operation_id") if isinstance(raw, dict) else None
    return str(value) if value else None


def _evidence_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


def verify_evidence_digest(evidence: LifecycleEvidence) -> bool:
    raw = asdict(evidence)
    supplied = raw.pop("evidence_sha256")
    raw["audit_sequences"] = list(raw["audit_sequences"])
    raw["anomalies"] = list(raw["anomalies"])
    return _evidence_digest(raw) == supplied


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

    sequences = tuple(int(item.get("seq", 0)) for item in relevant)
    kinds = [str(item.get("kind", "")) for item in relevant]
    admitted = _ADMITTED_KIND in kinds
    executed_count = sum(kind in _TERMINAL_AUDIT_KINDS for kind in kinds)
    executed = executed_count > 0
    failed = sum(kind == _FAILED_KIND for kind in kinds)
    deferred = sum(kind == _DEFERRED_KIND for kind in kinds)
    receipt_present = receipt is not None
    pending_present = pending is not None
    bound = bool(pending.get("executor_bound")) if pending is not None else False

    anomalies: list[str] = []
    if len(sequences) != len(set(sequences)):
        anomalies.append("duplicate_audit_sequence")
    if any(seq <= 0 for seq in sequences):
        anomalies.append("invalid_audit_sequence")
    if executed_count > 1:
        anomalies.append("duplicate_execution_audit")
    if executed and not receipt_present:
        anomalies.append("executed_without_receipt")
    if receipt_present and not executed:
        anomalies.append("receipt_without_execution_audit")
    if receipt_present and not admitted:
        anomalies.append("receipt_without_admission_audit")
    if executed and not admitted:
        anomalies.append("execution_without_admission_audit")
    if not pending_present and not receipt_present and admitted and not failed:
        anomalies.append("admitted_intent_missing")

    if receipt_present and not pending_present and executed:
        state, confidence = "confirmed", "high"
    elif receipt_present and pending_present:
        state, confidence = "executed_unconfirmed", "high" if executed else "medium"
    elif receipt_present:
        state, confidence = "receipt_unattested", "low"
    elif executed:
        state, confidence = "evidence_gap", "low"
    elif pending_present and bound:
        state, confidence = "pending_bound", "high"
    elif pending_present:
        state, confidence = "pending_unbound", "high"
    elif failed:
        state, confidence = "failed_not_pending", "medium"
    else:
        state, confidence = "unknown", "low"

    digest_payload = {
        "operation_id": operation_id,
        "state": state,
        "pending": pending_present,
        "executor_bound": bound,
        "receipt_present": receipt_present,
        "admitted_audit_present": admitted,
        "executed_audit_present": executed,
        "executed_audit_count": executed_count,
        "failed_audit_count": failed,
        "deferred_audit_count": deferred,
        "audit_sequences": list(sequences),
        "anomalies": anomalies,
        "confidence": confidence,
    }
    return LifecycleEvidence(
        operation_id=operation_id,
        state=state,
        pending=pending_present,
        executor_bound=bound,
        receipt_present=receipt_present,
        admitted_audit_present=admitted,
        executed_audit_present=executed,
        executed_audit_count=executed_count,
        failed_audit_count=failed,
        deferred_audit_count=deferred,
        audit_sequences=sequences,
        anomalies=tuple(anomalies),
        confidence=confidence,
        evidence_sha256=_evidence_digest(digest_payload),
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
