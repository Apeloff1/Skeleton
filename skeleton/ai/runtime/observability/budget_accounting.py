"""P1 quota and budget accounting qualification.

This module is a governed facade over the existing durable tenant quota ledger.
It does not replace quota authority. Reservations, incremental charges,
idempotency, restart safety, and reconciliation remain implemented by
SqliteTenantQuotaLedger.

The P1 layer adds a stable accounting receipt and a fail-closed qualification
step so duplicate/retry paths cannot become promotion evidence when accounting
is unresolved, over quota, overrun, or inconsistent with durable committed
usage.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import UsageEstimate
from skeleton.intelligence.quota import (
    QuotaCompletion,
    QuotaReservation,
    QuotaUsage,
    QuotaUsageEvent,
    TenantQuota,
)
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


BUDGET_ACCOUNTING_SCHEMA_VERSION = 1
BUDGET_ACCOUNTING_TASK_ID = "P1-DIST-05"
BUDGET_ACCOUNTING_ACCOUNTABILITY_ID = "ACC-P1-DIST-05"
_MAX_EVIDENCE = 256
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BudgetAccountingError(ValueError):
    """Budget accounting evidence is malformed or unsafe."""


def _text(value: object, field: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BudgetAccountingError(f"{field} must be non-empty")
    normalized = value.strip()
    if normalized != value or len(normalized) > maximum:
        raise BudgetAccountingError(f"{field} must be normalized")
    return normalized


def _token(value: object, field: str, *, maximum: int = 256) -> str:
    text = _text(value, field, maximum=maximum)
    if not _TOKEN_RE.fullmatch(text):
        raise BudgetAccountingError(f"{field} must be a canonical token")
    return text


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise BudgetAccountingError(
            f"{field} must be lowercase sha256"
        )
    return value


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BudgetAccountingError(
            f"{field} must be finite and non-negative"
        )
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise BudgetAccountingError(
            f"{field} must be finite and non-negative"
        )
    return result


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BudgetAccountingError(
            f"{field} must be a non-negative integer"
        )
    return value


def _canonical_digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise BudgetAccountingError(
            "budget accounting payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


def _evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise BudgetAccountingError(
            "evidence_refs must contain EvidenceRef values"
        )
    by_key: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in values:
        if not isinstance(item, EvidenceRef):
            raise BudgetAccountingError(
                "evidence_refs must contain EvidenceRef values"
            )
        _text(item.source, "evidence source")
        _sha256(item.digest, "evidence digest")
        _token(item.category, "evidence category", maximum=128)
        by_key[(item.source, item.digest, item.category)] = item
    if not by_key:
        raise BudgetAccountingError("evidence_refs must be non-empty")
    if len(by_key) > _MAX_EVIDENCE:
        raise BudgetAccountingError("evidence_refs exceeds item limit")
    return tuple(by_key[key] for key in sorted(by_key))


def _usage_covers(
    committed: dict[str, object],
    actual: QuotaUsage,
) -> tuple[str, ...]:
    reasons: list[str] = []
    actual_map = actual.as_dict()
    for field, expected in actual_map.items():
        value = committed.get(field)
        if isinstance(expected, float):
            try:
                observed = _finite_nonnegative(value, f"committed.{field}")
            except BudgetAccountingError:
                reasons.append(f"committed-usage-invalid:{field}")
                continue
            if observed + 1e-12 < float(expected):
                reasons.append(f"committed-usage-underflow:{field}")
        else:
            try:
                observed_int = _nonnegative_int(
                    value,
                    f"committed.{field}",
                )
            except BudgetAccountingError:
                reasons.append(f"committed-usage-invalid:{field}")
                continue
            if observed_int < int(expected):
                reasons.append(f"committed-usage-underflow:{field}")
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class BudgetAccountingDecision:
    accepted: bool
    reasons: tuple[str, ...]
    tenant_id: str
    window_id: str
    operation_id: str
    reservation_id: str
    reservation_digest: str
    completion_digest: str
    snapshot_digest: str
    actual_usage_digest: str
    usage_event_count: int
    evidence_refs: tuple[EvidenceRef, ...]
    task_id: str = BUDGET_ACCOUNTING_TASK_ID
    accountability_id: str = BUDGET_ACCOUNTING_ACCOUNTABILITY_ID
    schema_version: int = BUDGET_ACCOUNTING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise BudgetAccountingError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(item, str) or not item for item in self.reasons
        ):
            raise BudgetAccountingError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "tenant_id",
            "window_id",
            "operation_id",
            "reservation_id",
        ):
            object.__setattr__(
                self,
                field,
                _token(getattr(self, field), field),
            )
        for field in (
            "reservation_digest",
            "completion_digest",
            "snapshot_digest",
            "actual_usage_digest",
        ):
            object.__setattr__(
                self,
                field,
                _sha256(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "usage_event_count",
            _nonnegative_int(
                self.usage_event_count,
                "usage_event_count",
            ),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence(self.evidence_refs),
        )
        if self.task_id != BUDGET_ACCOUNTING_TASK_ID:
            raise BudgetAccountingError("task_id drift")
        if self.accountability_id != BUDGET_ACCOUNTING_ACCOUNTABILITY_ID:
            raise BudgetAccountingError("accountability_id drift")
        if self.schema_version != BUDGET_ACCOUNTING_SCHEMA_VERSION:
            raise BudgetAccountingError(
                "unsupported accounting decision schema"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "tenant_id": self.tenant_id,
            "window_id": self.window_id,
            "operation_id": self.operation_id,
            "reservation_id": self.reservation_id,
            "reservation_digest": self.reservation_digest,
            "completion_digest": self.completion_digest,
            "snapshot_digest": self.snapshot_digest,
            "actual_usage_digest": self.actual_usage_digest,
            "usage_event_count": self.usage_event_count,
            "evidence_refs": [
                {
                    "source": item.source,
                    "digest": item.digest,
                    "category": item.category,
                }
                for item in self.evidence_refs
            ],
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:dist-05:budget-accounting",
    ) -> EvidenceRef:
        if not self.accepted:
            raise BudgetAccountingError(
                "rejected budget accounting cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="budget_accounting",
        )


class DurableBudgetAccountingLedger:
    """Governed facade over SqliteTenantQuotaLedger."""

    def __init__(self, path: str | Path):
        self._ledger = SqliteTenantQuotaLedger(path)

    @property
    def ledger(self) -> SqliteTenantQuotaLedger:
        return self._ledger

    def configure(
        self,
        tenant_id: str,
        quota: TenantQuota,
        *,
        replace: bool = False,
    ) -> TenantQuota:
        return self._ledger.configure(
            tenant_id,
            quota,
            replace=replace,
        )

    def reserve(
        self,
        tenant_id: str,
        operation_id: str,
        estimate: UsageEstimate,
        *,
        now: float | None = None,
    ) -> QuotaReservation:
        return self._ledger.reserve(
            tenant_id,
            operation_id,
            estimate,
            now=now,
        )

    def charge(
        self,
        reservation_id: str,
        charge_id: str,
        category: str,
        delta: UsageEstimate,
        *,
        max_tool_calls: int | None = None,
        max_artifact_bytes: int | None = None,
        max_storage_bytes: int | None = None,
        now: float | None = None,
    ) -> QuotaUsageEvent:
        return self._ledger.record_usage_event(
            reservation_id,
            charge_id,
            category,
            delta,
            max_tool_calls=max_tool_calls,
            max_artifact_bytes=max_artifact_bytes,
            max_storage_bytes=max_storage_bytes,
            now=now,
        )

    def mark_charge_unknown(
        self,
        reservation_id: str,
        charge_id: str,
        category: str,
        *,
        now: float | None = None,
    ) -> QuotaUsageEvent:
        return self._ledger.mark_usage_unknown(
            reservation_id,
            charge_id,
            category,
            now=now,
        )

    def resolve_unknown_charge(
        self,
        reservation_id: str,
        charge_id: str,
        delta: UsageEstimate,
        *,
        max_tool_calls: int | None = None,
        max_artifact_bytes: int | None = None,
        max_storage_bytes: int | None = None,
        now: float | None = None,
    ) -> QuotaUsageEvent:
        return self._ledger.resolve_unknown_usage(
            reservation_id,
            charge_id,
            delta,
            max_tool_calls=max_tool_calls,
            max_artifact_bytes=max_artifact_bytes,
            max_storage_bytes=max_storage_bytes,
            now=now,
        )

    def reconcile(
        self,
        reservation_id: str,
        actual: UsageEstimate,
        *,
        now: float | None = None,
    ) -> QuotaCompletion:
        return self._ledger.complete(
            reservation_id,
            actual,
            now=now,
        )

    def snapshot(self, tenant_id: str) -> dict[str, object]:
        return self._ledger.snapshot(tenant_id)

    def qualification(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        reservation: QuotaReservation,
        completion: QuotaCompletion,
        evidence_refs: Iterable[EvidenceRef],
    ) -> BudgetAccountingDecision:
        snapshot = self.snapshot(tenant_id)
        return qualify_budget_accounting(
            tenant_id=tenant_id,
            operation_id=operation_id,
            reservation=reservation,
            completion=completion,
            snapshot=snapshot,
            evidence_refs=evidence_refs,
        )


def qualify_budget_accounting(
    *,
    tenant_id: str,
    operation_id: str,
    reservation: QuotaReservation,
    completion: QuotaCompletion,
    snapshot: dict[str, object],
    evidence_refs: Iterable[EvidenceRef],
) -> BudgetAccountingDecision:
    if not isinstance(reservation, QuotaReservation):
        raise TypeError("reservation must be QuotaReservation")
    if not isinstance(completion, QuotaCompletion):
        raise TypeError("completion must be QuotaCompletion")
    if not isinstance(snapshot, dict):
        raise TypeError("snapshot must be a dictionary")

    tenant = _token(tenant_id, "tenant_id")
    operation = _token(operation_id, "operation_id")
    refs = _evidence(evidence_refs)
    reasons: list[str] = []

    if reservation.tenant_id != tenant:
        reasons.append("reservation-tenant-mismatch")
    if reservation.operation_id != operation:
        reasons.append("reservation-operation-mismatch")
    if completion.tenant_id != tenant:
        reasons.append("completion-tenant-mismatch")
    if completion.operation_id != operation:
        reasons.append("completion-operation-mismatch")
    if completion.reservation_id != reservation.reservation_id:
        reasons.append("completion-reservation-mismatch")
    if completion.window_id != reservation.window_id:
        reasons.append("completion-window-mismatch")
    if completion.estimate != reservation.estimate:
        reasons.append("completion-estimate-mismatch")
    if completion.overrun:
        reasons.append(
            "completion-overrun:" + ",".join(completion.overrun_dimensions)
        )

    if snapshot.get("tenant_id") != tenant:
        reasons.append("snapshot-tenant-mismatch")
    if snapshot.get("window_id") != reservation.window_id:
        reasons.append("snapshot-window-mismatch")

    active = snapshot.get("active_reservations")
    completions = snapshot.get("completions")
    usage_events = snapshot.get("usage_events")
    unknown = snapshot.get("unknown_usage_events")
    over_quota = snapshot.get("over_quota_dimensions")
    committed = snapshot.get("committed")

    try:
        if _nonnegative_int(active, "active_reservations") != 0:
            reasons.append("active-reservation-remains")
    except BudgetAccountingError:
        reasons.append("snapshot-active-reservations-invalid")
    try:
        if _nonnegative_int(completions, "completions") < 1:
            reasons.append("completion-not-durable")
    except BudgetAccountingError:
        reasons.append("snapshot-completions-invalid")
    try:
        event_count = _nonnegative_int(usage_events, "usage_events")
    except BudgetAccountingError:
        event_count = 0
        reasons.append("snapshot-usage-events-invalid")
    if event_count < 1:
        reasons.append("no-durable-charge-events")
    try:
        if _nonnegative_int(unknown, "unknown_usage_events") != 0:
            reasons.append("unresolved-usage-events")
    except BudgetAccountingError:
        reasons.append("snapshot-unknown-usage-invalid")

    if not isinstance(over_quota, list):
        reasons.append("snapshot-over-quota-invalid")
    elif over_quota:
        reasons.append("snapshot-over-quota:" + ",".join(
            str(item) for item in over_quota
        ))

    if not isinstance(committed, dict):
        reasons.append("snapshot-committed-invalid")
    else:
        reasons.extend(_usage_covers(committed, completion.actual))

    normalized = tuple(sorted(set(reasons)))
    return BudgetAccountingDecision(
        accepted=not normalized,
        reasons=normalized,
        tenant_id=tenant,
        window_id=reservation.window_id,
        operation_id=operation,
        reservation_id=reservation.reservation_id,
        reservation_digest=_canonical_digest(reservation.as_dict()),
        completion_digest=_canonical_digest(completion.as_dict()),
        snapshot_digest=_canonical_digest(snapshot),
        actual_usage_digest=_canonical_digest(completion.actual.as_dict()),
        usage_event_count=event_count,
        evidence_refs=refs,
    )


__all__ = [
    "BUDGET_ACCOUNTING_ACCOUNTABILITY_ID",
    "BUDGET_ACCOUNTING_SCHEMA_VERSION",
    "BUDGET_ACCOUNTING_TASK_ID",
    "BudgetAccountingDecision",
    "BudgetAccountingError",
    "DurableBudgetAccountingLedger",
    "qualify_budget_accounting",
]
