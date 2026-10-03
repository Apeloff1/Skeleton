"""Integrated cost governor over the canonical admission and quota runtime.

VOL-186 does not introduce another ledger.  The governor composes the existing
AdmissionRuntime, tenant quota ledger, incremental usage metering, unknown-usage
fencing, terminal reconciliation, and budget-accounting qualification.

A cheaper fallback is attempted only for declared resource-budget failures.
Concurrency, queue, deadline, shared-pressure, identity, and accounting
failures are never bypassed by fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any, Iterable

from skeleton.ai.runtime.observability.budget_accounting import (
    BudgetAccountingDecision,
    qualify_budget_accounting,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import (
    AdmissionCompletion,
    AdmissionLease,
    AdmissionRuntime,
    AdmissionRuntimeConflict,
    AdmissionRuntimeError,
    UnknownUsageMarker,
)
from skeleton.intelligence.quota import (
    QuotaCompletion,
    QuotaConflict,
    QuotaError,
    QuotaReservation,
    QuotaUsage,
    QuotaUsageEvent,
    TenantQuota,
)
from skeleton.intelligence.quota_sqlite import SqliteTenantQuotaLedger


_SAFE_FALLBACK_REASON_PREFIXES = (
    "input_token_budget_exceeded",
    "output_token_budget_exceeded",
    "cost_budget_exceeded",
    "wall_time_budget_exceeded",
    "provider_attempt_budget_exceeded",
    "tool_call_budget_exceeded",
    "artifact_budget_exceeded",
    "storage_budget_exceeded",
    "tenant_quota_exceeded:",
)
_USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cost_usd",
    "wall_seconds",
    "provider_attempts",
    "tool_calls",
    "artifact_bytes",
    "storage_bytes",
)


class CostGovernorError(RuntimeError):
    """The cost-governor contract or integrated runtime transition failed."""


class CostGovernorDenied(CostGovernorError):
    """The requested or fallback work was denied by a governed budget."""


class CostGovernorConflict(CostGovernorError):
    """An idempotency, lease, or durable accounting conflict occurred."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CostGovernorError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise CostGovernorError(f"{name} exceeds maximum length")
    return value


def _sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CostGovernorError(f"{name} must be lowercase sha256")
    return value


def _canonical_json_text(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CostGovernorError(
            "cost-governor evidence must be canonical JSON"
        ) from exc


def _canonical_digest(value: object) -> str:
    raw = _canonical_json_text(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _usage_payload(usage: UsageEstimate) -> dict[str, int | float]:
    if not isinstance(usage, UsageEstimate):
        raise TypeError("usage must be UsageEstimate")
    return {
        field: getattr(usage, field)
        for field in _USAGE_FIELDS
    }


def _request_digest(request: AdmissionRequest) -> str:
    if not isinstance(request, AdmissionRequest):
        raise TypeError("request must be AdmissionRequest")
    return _canonical_digest(
        {
            "operation_id": request.operation_id,
            "tenant_id": request.tenant_id,
            "capability": request.capability,
            "budget": request.budget.as_dict(),
            "estimate": _usage_payload(request.estimate),
            "priority": request.priority,
            "deadline_monotonic": request.deadline_monotonic,
        }
    )


def _quota_reservation_digest(reservation: QuotaReservation | None) -> str | None:
    if reservation is None:
        return None
    return _canonical_digest(reservation.as_dict())


def _usage_event_digest(event: QuotaUsageEvent) -> str:
    return _canonical_digest(event.as_dict())


def _completion_digest(completion: QuotaCompletion | None) -> str | None:
    if completion is None:
        return None
    return _canonical_digest(completion.as_dict())


def _fallback_reason_allowed(reason: str, allowed: tuple[str, ...]) -> bool:
    return any(
        reason == prefix or reason.startswith(prefix)
        for prefix in allowed
    )


def _validated_evidence_refs(
    values: Iterable[EvidenceRef],
) -> tuple[EvidenceRef, ...]:
    if isinstance(values, (str, bytes)):
        raise CostGovernorError(
            "evidence_refs must contain EvidenceRef values"
        )
    refs = tuple(values)
    if not refs:
        raise CostGovernorError("evidence_refs must be non-empty")
    normalized: dict[tuple[str, str, str], EvidenceRef] = {}
    for item in refs:
        if not isinstance(item, EvidenceRef):
            raise CostGovernorError(
                "evidence_refs must contain EvidenceRef values"
            )
        source = _token("evidence source", item.source)
        digest = _sha256("evidence digest", item.digest)
        category = _token("evidence category", item.category)
        normalized[(source, digest, category)] = item
    return tuple(normalized[key] for key in sorted(normalized))


def _strictly_cheaper(
    requested: UsageEstimate,
    fallback: UsageEstimate,
) -> bool:
    less = False
    for field in _USAGE_FIELDS:
        before = getattr(requested, field)
        after = getattr(fallback, field)
        if after > before:
            return False
        if after < before:
            less = True
    return less


@dataclass(frozen=True, slots=True)
class SafeCostFallback:
    """Declared cheaper capability used only for bounded budget failures."""

    fallback_id: str
    capability: str
    estimate: UsageEstimate
    allowed_failure_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fallback_id",
            _token("fallback_id", self.fallback_id),
        )
        object.__setattr__(
            self,
            "capability",
            _token("capability", self.capability),
        )
        if not isinstance(self.estimate, UsageEstimate):
            raise CostGovernorError("estimate must be UsageEstimate")
        reasons = tuple(sorted(set(self.allowed_failure_reasons)))
        if not reasons:
            raise CostGovernorError(
                "allowed_failure_reasons must be non-empty"
            )
        for reason in reasons:
            clean = _token("allowed_failure_reason", reason)
            if clean not in _SAFE_FALLBACK_REASON_PREFIXES:
                raise CostGovernorError(
                    f"unsafe fallback failure reason:{clean}"
                )
        object.__setattr__(self, "allowed_failure_reasons", reasons)

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "fallback_id": self.fallback_id,
                "capability": self.capability,
                "estimate": _usage_payload(self.estimate),
                "allowed_failure_reasons": list(
                    self.allowed_failure_reasons
                ),
            }
        )


@dataclass(frozen=True, slots=True)
class CostReservation:
    """Receipt binding cost governance to one canonical admission lease."""

    operation_id: str
    tenant_id: str
    requested_capability: str
    selected_capability: str
    requested_request_digest: str
    selected_request_digest: str
    admission_decision_id: str
    lease_id: str
    quota_reservation_digest: str | None
    selected_estimate_digest: str
    fallback_used: bool
    fallback_id: str | None = None
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "operation_id",
            "tenant_id",
            "requested_capability",
            "selected_capability",
            "admission_decision_id",
            "lease_id",
        ):
            object.__setattr__(
                self,
                name,
                _token(name, getattr(self, name)),
            )
        for name in (
            "requested_request_digest",
            "selected_request_digest",
            "selected_estimate_digest",
        ):
            object.__setattr__(
                self,
                name,
                _sha256(name, getattr(self, name)),
            )
        if self.quota_reservation_digest is not None:
            object.__setattr__(
                self,
                "quota_reservation_digest",
                _sha256(
                    "quota_reservation_digest",
                    self.quota_reservation_digest,
                ),
            )
        if not isinstance(self.fallback_used, bool):
            raise CostGovernorError("fallback_used must be boolean")
        if self.fallback_used:
            object.__setattr__(
                self,
                "fallback_id",
                _token("fallback_id", self.fallback_id),
            )
            object.__setattr__(
                self,
                "fallback_reason",
                _token("fallback_reason", self.fallback_reason),
            )
            if self.requested_capability == self.selected_capability:
                raise CostGovernorError(
                    "fallback must select a distinct declared capability"
                )
        elif self.fallback_id is not None or self.fallback_reason is not None:
            raise CostGovernorError(
                "non-fallback reservation cannot carry fallback metadata"
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "operation_id": self.operation_id,
                "tenant_id": self.tenant_id,
                "requested_capability": self.requested_capability,
                "selected_capability": self.selected_capability,
                "requested_request_digest": self.requested_request_digest,
                "selected_request_digest": self.selected_request_digest,
                "admission_decision_id": self.admission_decision_id,
                "lease_id": self.lease_id,
                "quota_reservation_digest": self.quota_reservation_digest,
                "selected_estimate_digest": self.selected_estimate_digest,
                "fallback_used": self.fallback_used,
                "fallback_id": self.fallback_id,
                "fallback_reason": self.fallback_reason,
            }
        )


@dataclass(frozen=True, slots=True)
class CostCharge:
    """Idempotent durable incremental usage charge receipt."""

    operation_id: str
    event_id: str
    category: str
    usage_digest: str
    quota_event_digest: str
    resolved_unknown_usage: bool = False

    def __post_init__(self) -> None:
        for name in ("operation_id", "event_id", "category"):
            object.__setattr__(
                self,
                name,
                _token(name, getattr(self, name)),
            )
        object.__setattr__(
            self,
            "usage_digest",
            _sha256("usage_digest", self.usage_digest),
        )
        object.__setattr__(
            self,
            "quota_event_digest",
            _sha256("quota_event_digest", self.quota_event_digest),
        )
        if not isinstance(self.resolved_unknown_usage, bool):
            raise CostGovernorError(
                "resolved_unknown_usage must be boolean"
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "operation_id": self.operation_id,
                "event_id": self.event_id,
                "category": self.category,
                "usage_digest": self.usage_digest,
                "quota_event_digest": self.quota_event_digest,
                "resolved_unknown_usage": self.resolved_unknown_usage,
            }
        )


@dataclass(frozen=True, slots=True)
class CostDecision:
    """Terminal cost-governance evidence for completion or unspent release."""

    operation_id: str
    tenant_id: str
    state: str
    reservation_digest: str
    completion_digest: str | None
    accounting_decision_digest: str | None
    accepted: bool
    reasons: tuple[str, ...]
    promotion_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _token("operation_id", self.operation_id),
        )
        object.__setattr__(
            self,
            "tenant_id",
            _token("tenant_id", self.tenant_id),
        )
        if self.state not in {"completed", "released_unspent"}:
            raise CostGovernorError("unknown cost decision state")
        object.__setattr__(
            self,
            "reservation_digest",
            _sha256("reservation_digest", self.reservation_digest),
        )
        if self.completion_digest is not None:
            object.__setattr__(
                self,
                "completion_digest",
                _sha256("completion_digest", self.completion_digest),
            )
        if self.accounting_decision_digest is not None:
            object.__setattr__(
                self,
                "accounting_decision_digest",
                _sha256(
                    "accounting_decision_digest",
                    self.accounting_decision_digest,
                ),
            )
        if not isinstance(self.accepted, bool):
            raise CostGovernorError("accepted must be boolean")
        reasons = tuple(sorted(set(self.reasons)))
        if any(not isinstance(item, str) or not item for item in reasons):
            raise CostGovernorError(
                "reasons must contain non-empty strings"
            )
        object.__setattr__(self, "reasons", reasons)
        if self.state == "released_unspent":
            if self.completion_digest is not None:
                raise CostGovernorError(
                    "released reservation cannot carry completion"
                )
            if self.accounting_decision_digest is not None:
                raise CostGovernorError(
                    "released reservation cannot carry accounting decision"
                )
            if self.accepted:
                raise CostGovernorError(
                    "released reservation is not completed cost evidence"
                )
        else:
            if self.completion_digest is None:
                raise CostGovernorError(
                    "completed decision requires completion digest"
                )
            if self.accounting_decision_digest is None:
                raise CostGovernorError(
                    "completed decision requires accounting qualification"
                )
            if self.accepted != (not reasons):
                raise CostGovernorError(
                    "accepted state must match terminal reasons"
                )
        if self.promotion_authority is not False:
            raise CostGovernorError(
                "cost governor has no promotion authority"
            )

    @property
    def digest(self) -> str:
        return _canonical_digest(
            {
                "operation_id": self.operation_id,
                "tenant_id": self.tenant_id,
                "state": self.state,
                "reservation_digest": self.reservation_digest,
                "completion_digest": self.completion_digest,
                "accounting_decision_digest": self.accounting_decision_digest,
                "accepted": self.accepted,
                "reasons": list(self.reasons),
                "promotion_authority": False,
            }
        )


@dataclass(slots=True)
class _ActiveCostReservation:
    requested_request_digest: str
    receipt: CostReservation


class CostGovernor:
    """Integrated admission/quota governor with declared safe fallback."""

    def __init__(self, runtime: AdmissionRuntime) -> None:
        if not isinstance(runtime, AdmissionRuntime):
            raise TypeError("runtime must be AdmissionRuntime")
        self.runtime = runtime
        self._lock = threading.RLock()
        self._active: dict[str, _ActiveCostReservation] = {}

    @classmethod
    def durable(
        cls,
        path: str | Path,
        *,
        default_tenant_quota: TenantQuota,
    ) -> "CostGovernor":
        if not isinstance(default_tenant_quota, TenantQuota):
            raise TypeError(
                "default_tenant_quota must be TenantQuota"
            )
        ledger = SqliteTenantQuotaLedger(path)
        runtime = AdmissionRuntime(
            quota_ledger=ledger,
            default_tenant_quota=default_tenant_quota,
        )
        return cls(runtime)

    @staticmethod
    def _receipt(
        *,
        requested: AdmissionRequest,
        selected: AdmissionRequest,
        lease: AdmissionLease,
        fallback: SafeCostFallback | None,
        fallback_reason: str | None,
    ) -> CostReservation:
        reservation = lease.quota_reservation
        return CostReservation(
            operation_id=requested.operation_id,
            tenant_id=requested.tenant_id,
            requested_capability=requested.capability,
            selected_capability=selected.capability,
            requested_request_digest=_request_digest(requested),
            selected_request_digest=_request_digest(selected),
            admission_decision_id=lease.decision.decision_id,
            lease_id=lease.lease_id,
            quota_reservation_digest=_quota_reservation_digest(reservation),
            selected_estimate_digest=_canonical_digest(
                _usage_payload(selected.estimate)
            ),
            fallback_used=fallback is not None,
            fallback_id=None if fallback is None else fallback.fallback_id,
            fallback_reason=fallback_reason,
        )

    @staticmethod
    def _fallback_request(
        requested: AdmissionRequest,
        fallback: SafeCostFallback,
    ) -> AdmissionRequest:
        if fallback.capability == requested.capability:
            raise CostGovernorError(
                "fallback must declare a distinct reduced capability"
            )
        if not _strictly_cheaper(
            requested.estimate,
            fallback.estimate,
        ):
            raise CostGovernorError(
                "fallback estimate must be component-wise no greater and strictly cheaper"
            )
        return replace(
            requested,
            capability=fallback.capability,
            estimate=fallback.estimate,
        )

    def reserve(
        self,
        request: AdmissionRequest,
        *,
        fallback: SafeCostFallback | None = None,
        now_monotonic: float | None = None,
        now_wall: float | None = None,
    ) -> CostReservation:
        if not isinstance(request, AdmissionRequest):
            raise TypeError("request must be AdmissionRequest")
        if fallback is not None and not isinstance(
            fallback,
            SafeCostFallback,
        ):
            raise TypeError("fallback must be SafeCostFallback")
        requested_digest = _request_digest(request)

        with self._lock:
            current = self._active.get(request.operation_id)
            if current is not None:
                if current.requested_request_digest != requested_digest:
                    raise CostGovernorError(
                        "operation already has a cost reservation with different requested inputs"
                    )
                return current.receipt

            try:
                lease = self.runtime.admit(
                    request,
                    now_monotonic=now_monotonic,
                    now_wall=now_wall,
                )
                receipt = self._receipt(
                    requested=request,
                    selected=request,
                    lease=lease,
                    fallback=None,
                    fallback_reason=None,
                )
            except AdmissionError as original_exc:
                reason = str(original_exc)
                if fallback is None:
                    raise CostGovernorDenied(reason) from original_exc
                if not _fallback_reason_allowed(
                    reason,
                    fallback.allowed_failure_reasons,
                ):
                    raise CostGovernorDenied(reason) from original_exc
                selected = self._fallback_request(
                    request,
                    fallback,
                )
                try:
                    lease = self.runtime.admit(
                        selected,
                        now_monotonic=now_monotonic,
                        now_wall=now_wall,
                    )
                except AdmissionError as fallback_exc:
                    raise CostGovernorDenied(
                        f"declared_cost_fallback_denied:{fallback_exc}"
                    ) from fallback_exc
                except AdmissionRuntimeConflict as fallback_exc:
                    raise CostGovernorConflict(
                        f"declared_cost_fallback_conflict:{fallback_exc}"
                    ) from fallback_exc
                except AdmissionRuntimeError as fallback_exc:
                    raise CostGovernorError(
                        f"declared_cost_fallback_runtime_error:{fallback_exc}"
                    ) from fallback_exc
                receipt = self._receipt(
                    requested=request,
                    selected=selected,
                    lease=lease,
                    fallback=fallback,
                    fallback_reason=reason,
                )
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc

            self._active[request.operation_id] = _ActiveCostReservation(
                requested_request_digest=requested_digest,
                receipt=receipt,
            )
            return receipt

    def charge(
        self,
        operation_id: str,
        event_id: str,
        category: str,
        delta: UsageEstimate,
        *,
        now_wall: float | None = None,
    ) -> CostCharge:
        operation = _token("operation_id", operation_id)
        event = _token("event_id", event_id)
        clean_category = _token("category", category)
        if not isinstance(delta, UsageEstimate):
            raise TypeError("delta must be UsageEstimate")
        with self._lock:
            if operation not in self._active:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                recorded = self.runtime.record_usage_event(
                    operation,
                    event,
                    clean_category,
                    delta,
                    now_wall=now_wall,
                )
            except AdmissionError as exc:
                raise CostGovernorDenied(str(exc)) from exc
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc
        return CostCharge(
            operation_id=operation,
            event_id=event,
            category=recorded.category,
            usage_digest=_canonical_digest(
                _usage_payload(delta)
            ),
            quota_event_digest=_usage_event_digest(recorded),
        )

    def mark_usage_unknown(
        self,
        operation_id: str,
        event_id: str,
        category: str,
        reason: str,
        *,
        now_wall: float | None = None,
    ) -> UnknownUsageMarker:
        operation = _token("operation_id", operation_id)
        with self._lock:
            if operation not in self._active:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                return self.runtime.mark_usage_unknown(
                    operation,
                    event_id,
                    category,
                    reason,
                    now_wall=now_wall,
                )
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc

    def resolve_unknown_usage(
        self,
        operation_id: str,
        event_id: str,
        delta: UsageEstimate,
        *,
        now_wall: float | None = None,
    ) -> CostCharge:
        operation = _token("operation_id", operation_id)
        event = _token("event_id", event_id)
        if not isinstance(delta, UsageEstimate):
            raise TypeError("delta must be UsageEstimate")
        with self._lock:
            if operation not in self._active:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                recorded = self.runtime.resolve_unknown_usage(
                    operation,
                    event,
                    delta,
                    now_wall=now_wall,
                )
            except AdmissionError as exc:
                raise CostGovernorDenied(str(exc)) from exc
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc
        return CostCharge(
            operation_id=operation,
            event_id=event,
            category=recorded.category,
            usage_digest=_canonical_digest(
                _usage_payload(delta)
            ),
            quota_event_digest=_usage_event_digest(recorded),
            resolved_unknown_usage=True,
        )

    def complete(
        self,
        operation_id: str,
        actual: UsageEstimate,
        *,
        evidence_refs: Iterable[EvidenceRef],
        now_wall: float | None = None,
    ) -> CostDecision:
        operation = _token("operation_id", operation_id)
        if not isinstance(actual, UsageEstimate):
            raise TypeError("actual must be UsageEstimate")
        refs = _validated_evidence_refs(evidence_refs)
        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                completion: AdmissionCompletion = self.runtime.complete(
                    operation,
                    actual,
                    now_wall=now_wall,
                )
            except AdmissionRuntimeConflict as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                raise CostGovernorError(str(exc)) from exc

            # The runtime lease is terminal after complete(). From this point on
            # the governor must never retain a stale active reservation.
            self._active.pop(operation, None)
            try:
                quota_completion = completion.quota_completion
                quota_reservation = completion.lease.quota_reservation
                if quota_completion is None or quota_reservation is None:
                    raise CostGovernorError(
                        "cost completion requires durable quota accounting"
                    )
                ledger = self.runtime.quota_ledger
                if ledger is None:
                    raise CostGovernorError(
                        "cost completion requires quota ledger"
                    )
                snapshot = ledger.snapshot(completion.lease.tenant_id)
                accounting: BudgetAccountingDecision = qualify_budget_accounting(
                    tenant_id=completion.lease.tenant_id,
                    operation_id=operation,
                    reservation=quota_reservation,
                    completion=quota_completion,
                    snapshot=snapshot,
                    evidence_refs=refs,
                )
                reasons = list(accounting.reasons)
                if quota_completion.overrun:
                    reasons.append(
                        "cost-overrun:"
                        + ",".join(quota_completion.overrun_dimensions)
                    )
                normalized = tuple(sorted(set(reasons)))
                return CostDecision(
                    operation_id=operation,
                    tenant_id=completion.lease.tenant_id,
                    state="completed",
                    reservation_digest=active.receipt.digest,
                    completion_digest=_completion_digest(quota_completion),
                    accounting_decision_digest=accounting.decision_digest,
                    accepted=not normalized,
                    reasons=normalized,
                )
            except CostGovernorError:
                raise
            except Exception as exc:
                raise CostGovernorError(
                    "terminal_accounting_qualification_failed"
                ) from exc

    def release_unspent(
        self,
        operation_id: str,
    ) -> CostDecision:
        operation = _token("operation_id", operation_id)
        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            try:
                lease = self.runtime.release(operation)
            except (AdmissionRuntimeConflict, QuotaConflict) as exc:
                raise CostGovernorConflict(str(exc)) from exc
            except (AdmissionRuntimeError, QuotaError) as exc:
                raise CostGovernorError(str(exc)) from exc
            decision = CostDecision(
                operation_id=operation,
                tenant_id=lease.tenant_id,
                state="released_unspent",
                reservation_digest=active.receipt.digest,
                completion_digest=None,
                accounting_decision_digest=None,
                accepted=False,
                reasons=("reservation-released-unspent",),
            )
            self._active.pop(operation, None)
            return decision

    def active_reservations(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._active))


__all__ = [
    "CostCharge",
    "CostDecision",
    "CostGovernor",
    "CostGovernorConflict",
    "CostGovernorDenied",
    "CostGovernorError",
    "CostReservation",
    "SafeCostFallback",
]
