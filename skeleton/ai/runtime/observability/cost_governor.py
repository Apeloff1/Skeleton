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
import math
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
    AdmissionDecision,
    AdmissionError,
    AdmissionRequest,
    AdmissionStatus,
    ResourceBudget,
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
from skeleton.intelligence.shared_pressure import (
    SharedPressureLease,
    SqliteSharedPressureLedger,
)


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


def _usage_from_payload(value: object) -> UsageEstimate:
    if not isinstance(value, dict):
        raise CostGovernorError("usage journal payload is invalid")
    try:
        return UsageEstimate(
            input_tokens=int(value["input_tokens"]),
            output_tokens=int(value["output_tokens"]),
            cost_usd=float(value["cost_usd"]),
            wall_seconds=float(value["wall_seconds"]),
            provider_attempts=int(value["provider_attempts"]),
            tool_calls=int(value["tool_calls"]),
            artifact_bytes=int(value["artifact_bytes"]),
            storage_bytes=int(value["storage_bytes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "usage journal payload is invalid"
        ) from exc


def _budget_from_payload(value: object) -> ResourceBudget:
    if not isinstance(value, dict):
        raise CostGovernorError("budget journal payload is invalid")
    try:
        return ResourceBudget(
            max_input_tokens=int(value["max_input_tokens"]),
            max_output_tokens=int(value["max_output_tokens"]),
            max_cost_usd=float(value["max_cost_usd"]),
            max_wall_seconds=float(value["max_wall_seconds"]),
            max_provider_attempts=int(value["max_provider_attempts"]),
            max_tool_calls=int(value["max_tool_calls"]),
            max_artifact_bytes=int(value["max_artifact_bytes"]),
            max_storage_bytes=int(value["max_storage_bytes"]),
            max_concurrency=int(value["max_concurrency"]),
            max_queue_depth=int(value["max_queue_depth"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "budget journal payload is invalid"
        ) from exc


def _effective_terminal_actual(
    reported: UsageEstimate,
    completion: QuotaCompletion,
) -> UsageEstimate:
    observed = completion.actual
    return UsageEstimate(
        input_tokens=max(reported.input_tokens, observed.input_tokens),
        output_tokens=max(reported.output_tokens, observed.output_tokens),
        cost_usd=max(reported.cost_usd, observed.cost_usd),
        wall_seconds=reported.wall_seconds,
        provider_attempts=reported.provider_attempts,
        tool_calls=max(reported.tool_calls, observed.tool_calls),
        artifact_bytes=max(
            reported.artifact_bytes,
            observed.artifact_bytes,
        ),
        storage_bytes=max(
            reported.storage_bytes,
            observed.storage_bytes,
        ),
    )


def _budget_overrun_dimensions(
    budget: ResourceBudget,
    actual: UsageEstimate,
) -> tuple[str, ...]:
    limits: dict[str, int | float] = {
        "input_tokens": budget.max_input_tokens,
        "output_tokens": budget.max_output_tokens,
        "cost_usd": budget.max_cost_usd,
        "wall_seconds": budget.max_wall_seconds,
        "provider_attempts": budget.max_provider_attempts,
        "tool_calls": budget.max_tool_calls,
        "artifact_bytes": budget.max_artifact_bytes,
        "storage_bytes": budget.max_storage_bytes,
    }
    exceeded: list[str] = []
    for field, limit in limits.items():
        value = getattr(actual, field)
        if field in {"cost_usd", "wall_seconds"}:
            if float(value) > float(limit) + 1e-12:
                exceeded.append(field)
        elif int(value) > int(limit):
            exceeded.append(field)
    return tuple(exceeded)


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

    def as_dict(self) -> dict[str, Any]:
        return {
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

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


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

    def as_dict(self) -> dict[str, Any]:
        return {
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

    @property
    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


def _quota_usage_from_payload(value: object) -> QuotaUsage:
    if not isinstance(value, dict):
        raise CostGovernorError("quota usage journal payload is invalid")
    try:
        return QuotaUsage(
            operations=int(value["operations"]),
            input_tokens=int(value["input_tokens"]),
            output_tokens=int(value["output_tokens"]),
            cost_usd=float(value["cost_usd"]),
            tool_calls=int(value["tool_calls"]),
            artifact_bytes=int(value["artifact_bytes"]),
            storage_bytes=int(value["storage_bytes"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "quota usage journal payload is invalid"
        ) from exc


def _quota_reservation_from_payload(value: object) -> QuotaReservation:
    if not isinstance(value, dict):
        raise CostGovernorError(
            "quota reservation journal payload is invalid"
        )
    try:
        return QuotaReservation(
            reservation_id=str(value["reservation_id"]),
            tenant_id=str(value["tenant_id"]),
            window_id=str(value["window_id"]),
            operation_id=str(value["operation_id"]),
            estimate=_quota_usage_from_payload(value["estimate"]),
            reserved_at=float(value["reserved_at"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "quota reservation journal payload is invalid"
        ) from exc


def _cost_reservation_from_payload(value: object) -> CostReservation:
    if not isinstance(value, dict):
        raise CostGovernorError("cost reservation journal payload is invalid")
    try:
        return CostReservation(
            operation_id=value["operation_id"],
            tenant_id=value["tenant_id"],
            requested_capability=value["requested_capability"],
            selected_capability=value["selected_capability"],
            requested_request_digest=value["requested_request_digest"],
            selected_request_digest=value["selected_request_digest"],
            admission_decision_id=value["admission_decision_id"],
            lease_id=value["lease_id"],
            quota_reservation_digest=value.get("quota_reservation_digest"),
            selected_estimate_digest=value["selected_estimate_digest"],
            fallback_used=value["fallback_used"],
            fallback_id=value.get("fallback_id"),
            fallback_reason=value.get("fallback_reason"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "cost reservation journal payload is invalid"
        ) from exc


def _cost_decision_from_payload(value: object) -> CostDecision:
    if not isinstance(value, dict):
        raise CostGovernorError("cost decision journal payload is invalid")
    try:
        return CostDecision(
            operation_id=value["operation_id"],
            tenant_id=value["tenant_id"],
            state=value["state"],
            reservation_digest=value["reservation_digest"],
            completion_digest=value.get("completion_digest"),
            accounting_decision_digest=value.get(
                "accounting_decision_digest"
            ),
            accepted=value["accepted"],
            reasons=tuple(value["reasons"]),
            promotion_authority=value.get(
                "promotion_authority",
                False,
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "cost decision journal payload is invalid"
        ) from exc


def _evidence_digest(refs: tuple[EvidenceRef, ...]) -> str:
    return _canonical_digest(
        [
            {
                "source": item.source,
                "digest": item.digest,
                "category": item.category,
            }
            for item in refs
        ]
    )


@dataclass(frozen=True, slots=True)
class _RuntimeLeaseJournal:
    lease_id: str
    decision_id: str
    reason_code: str
    remaining: tuple[tuple[str, int | float], ...]
    admitted_at: float
    shared_pressure_lease: SharedPressureLease | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "decision_id": self.decision_id,
            "reason_code": self.reason_code,
            "remaining": dict(self.remaining),
            "admitted_at": self.admitted_at,
            "shared_pressure_lease": (
                None
                if self.shared_pressure_lease is None
                else {
                    "lease_id": self.shared_pressure_lease.lease_id,
                    "scope": self.shared_pressure_lease.scope,
                    "operation_id": self.shared_pressure_lease.operation_id,
                    "tenant_id": self.shared_pressure_lease.tenant_id,
                    "owner_id": self.shared_pressure_lease.owner_id,
                    "priority": self.shared_pressure_lease.priority,
                    "acquired_at": self.shared_pressure_lease.acquired_at,
                    "expires_at": self.shared_pressure_lease.expires_at,
                }
            ),
        }


def _runtime_lease_journal(
    lease: AdmissionLease,
) -> _RuntimeLeaseJournal:
    if not isinstance(lease, AdmissionLease):
        raise TypeError("runtime_lease must be AdmissionLease")
    remaining: list[tuple[str, int | float]] = []
    for key, value in sorted(lease.decision.remaining.items()):
        clean_key = _token("remaining key", key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise CostGovernorError(
                "runtime lease remaining budget is invalid"
            )
        remaining.append((clean_key, value))
    admitted_at = float(lease.admitted_at)
    if not math.isfinite(admitted_at) or admitted_at < 0:
        raise CostGovernorError("runtime lease admitted_at is invalid")

    pressure = lease.shared_pressure_lease
    if pressure is not None:
        for field_name in (
            "lease_id",
            "scope",
            "operation_id",
            "tenant_id",
            "owner_id",
        ):
            _token(
                "shared pressure " + field_name,
                getattr(pressure, field_name),
            )
        if (
            pressure.operation_id != lease.operation_id
            or pressure.tenant_id != lease.tenant_id
            or isinstance(pressure.priority, bool)
            or not isinstance(pressure.priority, int)
            or not 0 <= pressure.priority <= 1000
            or not math.isfinite(float(pressure.acquired_at))
            or float(pressure.acquired_at) < 0
            or not math.isfinite(float(pressure.expires_at))
            or float(pressure.expires_at) <= float(pressure.acquired_at)
        ):
            raise CostGovernorError(
                "runtime shared pressure lease is invalid"
            )

    return _RuntimeLeaseJournal(
        lease_id=_token("lease_id", lease.lease_id),
        decision_id=_token(
            "admission_decision_id",
            lease.decision.decision_id,
        ),
        reason_code=_token(
            "admission_reason_code",
            lease.decision.reason_code,
        ),
        remaining=tuple(remaining),
        admitted_at=admitted_at,
        shared_pressure_lease=lease.shared_pressure_lease,
    )


def _runtime_lease_journal_from_payload(
    value: object,
) -> _RuntimeLeaseJournal:
    if not isinstance(value, dict):
        raise CostGovernorError(
            "runtime lease journal payload is invalid"
        )
    remaining_raw = value.get("remaining")
    if not isinstance(remaining_raw, dict):
        raise CostGovernorError(
            "runtime lease remaining payload is invalid"
        )
    remaining: list[tuple[str, int | float]] = []
    for key, item in sorted(remaining_raw.items()):
        clean_key = _token("remaining key", key)
        if (
            isinstance(item, bool)
            or not isinstance(item, (int, float))
            or not math.isfinite(float(item))
            or float(item) < 0
        ):
            raise CostGovernorError(
                "runtime lease remaining payload is invalid"
            )
        remaining.append((clean_key, item))
    try:
        admitted_at = float(value["admitted_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "runtime lease admitted_at payload is invalid"
        ) from exc
    if not math.isfinite(admitted_at) or admitted_at < 0:
        raise CostGovernorError(
            "runtime lease admitted_at payload is invalid"
        )
    try:
        lease_id = value["lease_id"]
        decision_id = value["decision_id"]
        reason_code = value["reason_code"]
    except KeyError as exc:
        raise CostGovernorError(
            "runtime lease journal payload is invalid"
        ) from exc

    pressure_raw = value.get("shared_pressure_lease")
    pressure_lease: SharedPressureLease | None = None
    if pressure_raw is not None:
        if not isinstance(pressure_raw, dict):
            raise CostGovernorError(
                "shared pressure lease journal payload is invalid"
            )
        try:
            priority = pressure_raw["priority"]
            acquired_at = float(pressure_raw["acquired_at"])
            expires_at = float(pressure_raw["expires_at"])
            pressure_lease = SharedPressureLease(
                lease_id=_token(
                    "shared pressure lease_id",
                    pressure_raw["lease_id"],
                ),
                scope=_token(
                    "shared pressure scope",
                    pressure_raw["scope"],
                ),
                operation_id=_token(
                    "shared pressure operation_id",
                    pressure_raw["operation_id"],
                ),
                tenant_id=_token(
                    "shared pressure tenant_id",
                    pressure_raw["tenant_id"],
                ),
                owner_id=_token(
                    "shared pressure owner_id",
                    pressure_raw["owner_id"],
                ),
                priority=int(priority),
                acquired_at=acquired_at,
                expires_at=expires_at,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CostGovernorError(
                "shared pressure lease journal payload is invalid"
            ) from exc
        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
            or not 0 <= priority <= 1000
            or not math.isfinite(acquired_at)
            or acquired_at < 0
            or not math.isfinite(expires_at)
            or expires_at <= acquired_at
        ):
            raise CostGovernorError(
                "shared pressure lease journal payload is invalid"
            )

    return _RuntimeLeaseJournal(
        lease_id=_token("lease_id", lease_id),
        decision_id=_token("admission_decision_id", decision_id),
        reason_code=_token("admission_reason_code", reason_code),
        remaining=tuple(remaining),
        admitted_at=admitted_at,
        shared_pressure_lease=pressure_lease,
    )


@dataclass(frozen=True, slots=True)
class _CostCompletionIntent:
    actual: UsageEstimate
    budget: ResourceBudget
    evidence_digest: str


def _completion_intent_from_payload(
    value: object,
) -> _CostCompletionIntent:
    if not isinstance(value, dict):
        raise CostGovernorError(
            "completion intent journal payload is invalid"
        )
    try:
        evidence = _sha256(
            "completion intent evidence_digest",
            value["evidence_digest"],
        )
        return _CostCompletionIntent(
            actual=_usage_from_payload(value["actual"]),
            budget=_budget_from_payload(value["budget"]),
            evidence_digest=evidence,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CostGovernorError(
            "completion intent journal payload is invalid"
        ) from exc


@dataclass(frozen=True, slots=True)
class _CostJournalRecord:
    operation_id: str
    tenant_id: str
    requested_request_digest: str
    reservation: CostReservation
    quota_reservation: QuotaReservation
    state: str
    terminal: CostDecision | None
    evidence_digest: str | None
    completion_intent: _CostCompletionIntent | None
    runtime_lease: _RuntimeLeaseJournal | None


class _SqliteCostGovernorJournal:
    """Durable metadata journal; spend authority stays in quota tables."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS cost_governor_journal (
        operation_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        requested_request_digest TEXT NOT NULL,
        reservation_json TEXT NOT NULL,
        quota_reservation_json TEXT NOT NULL,
        state TEXT NOT NULL,
        terminal_json TEXT,
        evidence_digest TEXT,
        completion_intent_json TEXT,
        runtime_lease_json TEXT,
        CHECK (
            state IN (
                'active',
                'release_pending',
                'completed',
                'released_unspent'
            )
        )
    );
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with self._connect() as conn:
            conn.execute(self._SCHEMA)
            columns = {
                str(row["name"])
                for row in conn.execute(
                    "PRAGMA table_info(cost_governor_journal)"
                ).fetchall()
            }
            if "completion_intent_json" not in columns:
                conn.execute(
                    """
                    ALTER TABLE cost_governor_journal
                    ADD COLUMN completion_intent_json TEXT
                    """
                )
            if "runtime_lease_json" not in columns:
                conn.execute(
                    """
                    ALTER TABLE cost_governor_journal
                    ADD COLUMN runtime_lease_json TEXT
                    """
                )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @staticmethod
    def _decode_json(raw: object, field: str) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise CostGovernorError(f"{field} journal value is invalid")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CostGovernorError(
                f"{field} journal value is invalid"
            ) from exc
        if not isinstance(value, dict):
            raise CostGovernorError(f"{field} journal value is invalid")
        return value

    @classmethod
    def _record(cls, row: sqlite3.Row) -> _CostJournalRecord:
        terminal = (
            None
            if row["terminal_json"] is None
            else _cost_decision_from_payload(
                cls._decode_json(row["terminal_json"], "terminal")
            )
        )
        return _CostJournalRecord(
            operation_id=str(row["operation_id"]),
            tenant_id=str(row["tenant_id"]),
            requested_request_digest=str(
                row["requested_request_digest"]
            ),
            reservation=_cost_reservation_from_payload(
                cls._decode_json(row["reservation_json"], "reservation")
            ),
            quota_reservation=_quota_reservation_from_payload(
                cls._decode_json(
                    row["quota_reservation_json"],
                    "quota_reservation",
                )
            ),
            state=str(row["state"]),
            terminal=terminal,
            evidence_digest=(
                None
                if row["evidence_digest"] is None
                else str(row["evidence_digest"])
            ),
            completion_intent=(
                None
                if row["completion_intent_json"] is None
                else _completion_intent_from_payload(
                    cls._decode_json(
                        row["completion_intent_json"],
                        "completion_intent",
                    )
                )
            ),
            runtime_lease=(
                None
                if row["runtime_lease_json"] is None
                else _runtime_lease_journal_from_payload(
                    cls._decode_json(
                        row["runtime_lease_json"],
                        "runtime_lease",
                    )
                )
            ),
        )

    def load(self, operation_id: str) -> _CostJournalRecord | None:
        operation = _token("operation_id", operation_id)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM cost_governor_journal
                WHERE operation_id = ?
                """,
                (operation,),
            ).fetchone()
        return None if row is None else self._record(row)

    def quota_reservation_exists(
        self,
        reservation: QuotaReservation,
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT reserved_at FROM quota_reservations
                WHERE reservation_id = ?
                """,
                (reservation.reservation_id,),
            ).fetchone()
        if row is None:
            return False
        return float(row["reserved_at"]) == reservation.reserved_at

    def mark_release_pending(
        self,
        operation_id: str,
        reservation: CostReservation,
    ) -> _CostJournalRecord:
        operation = _token("operation_id", operation_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (operation,),
                ).fetchone()
                if row is None:
                    raise CostGovernorError(
                        "release requires active cost journal"
                    )
                existing = self._record(row)
                if existing.reservation != reservation:
                    raise CostGovernorConflict(
                        "release journal receipt mismatch"
                    )
                if existing.completion_intent is not None:
                    raise CostGovernorConflict(
                        "completion intent cannot be released as unspent"
                    )
                if existing.state == "active":
                    conn.execute(
                        """
                        UPDATE cost_governor_journal
                        SET state = 'release_pending'
                        WHERE operation_id = ?
                        """,
                        (operation,),
                    )
                elif existing.state != "release_pending":
                    raise CostGovernorConflict(
                        "terminal cost journal cannot enter release"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(operation)
        if loaded is None:
            raise CostGovernorError("release-pending journal write was lost")
        return loaded

    def revert_release_pending(
        self,
        operation_id: str,
    ) -> _CostJournalRecord:
        operation = _token("operation_id", operation_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (operation,),
                ).fetchone()
                if row is None:
                    raise CostGovernorError(
                        "release rollback requires cost journal"
                    )
                existing = self._record(row)
                if existing.state == "release_pending":
                    conn.execute(
                        """
                        UPDATE cost_governor_journal
                        SET state = 'active'
                        WHERE operation_id = ?
                        """,
                        (operation,),
                    )
                elif existing.state != "active":
                    raise CostGovernorConflict(
                        "terminal cost journal cannot roll back release"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(operation)
        if loaded is None:
            raise CostGovernorError("release rollback journal write was lost")
        return loaded

    def record_active(
        self,
        *,
        requested_request_digest: str,
        reservation: CostReservation,
        quota_reservation: QuotaReservation,
        runtime_lease: AdmissionLease,
    ) -> _CostJournalRecord:
        requested = _sha256(
            "requested_request_digest",
            requested_request_digest,
        )
        reservation_json = _canonical_json_text(reservation.as_dict())
        quota_json = _canonical_json_text(quota_reservation.as_dict())
        runtime_lease_record = _runtime_lease_journal(runtime_lease)
        runtime_lease_json = _canonical_json_text(
            runtime_lease_record.as_dict()
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (reservation.operation_id,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """
                        INSERT INTO cost_governor_journal (
                            operation_id, tenant_id,
                            requested_request_digest,
                            reservation_json, quota_reservation_json,
                            state, terminal_json, evidence_digest,
                            runtime_lease_json
                        ) VALUES (?, ?, ?, ?, ?, 'active', NULL, NULL, ?)
                        """,
                        (
                            reservation.operation_id,
                            reservation.tenant_id,
                            requested,
                            reservation_json,
                            quota_json,
                            runtime_lease_json,
                        ),
                    )
                else:
                    existing = self._record(row)
                    if existing.state != "active":
                        raise CostGovernorConflict(
                            "operation already has terminal cost journal state"
                        )
                    if (
                        existing.requested_request_digest != requested
                        or existing.reservation != reservation
                        or existing.quota_reservation != quota_reservation
                        or existing.runtime_lease != runtime_lease_record
                    ):
                        raise CostGovernorConflict(
                            "active cost journal replayed with different inputs"
                        )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(reservation.operation_id)
        if loaded is None:
            raise CostGovernorError("cost journal active write was lost")
        return loaded

    def record_completion_intent(
        self,
        operation_id: str,
        *,
        actual: UsageEstimate,
        budget: ResourceBudget,
        evidence_digest: str,
    ) -> _CostJournalRecord:
        operation = _token("operation_id", operation_id)
        if not isinstance(actual, UsageEstimate):
            raise TypeError("actual must be UsageEstimate")
        if not isinstance(budget, ResourceBudget):
            raise TypeError("budget must be ResourceBudget")
        evidence = _sha256("evidence_digest", evidence_digest)
        payload = _canonical_json_text(
            {
                "actual": _usage_payload(actual),
                "budget": budget.as_dict(),
                "evidence_digest": evidence,
            }
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (operation,),
                ).fetchone()
                if row is None:
                    raise CostGovernorError(
                        "completion intent requires active cost journal"
                    )
                existing = self._record(row)
                if existing.state != "active":
                    raise CostGovernorConflict(
                        "terminal cost journal cannot accept completion intent"
                    )
                requested = _CostCompletionIntent(
                    actual=actual,
                    budget=budget,
                    evidence_digest=evidence,
                )
                if existing.completion_intent is None:
                    conn.execute(
                        """
                        UPDATE cost_governor_journal
                        SET completion_intent_json = ?
                        WHERE operation_id = ?
                        """,
                        (payload, operation),
                    )
                elif existing.completion_intent != requested:
                    raise CostGovernorConflict(
                        "completion intent replayed with different inputs"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(operation)
        if loaded is None:
            raise CostGovernorError("completion intent write was lost")
        return loaded

    def clear_completion_intent(
        self,
        operation_id: str,
    ) -> _CostJournalRecord:
        operation = _token("operation_id", operation_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (operation,),
                ).fetchone()
                if row is None:
                    raise CostGovernorError(
                        "completion intent clear requires cost journal"
                    )
                existing = self._record(row)
                if existing.terminal is not None:
                    raise CostGovernorConflict(
                        "terminal cost journal cannot clear completion intent"
                    )
                conn.execute(
                    """
                    UPDATE cost_governor_journal
                    SET completion_intent_json = NULL
                    WHERE operation_id = ?
                    """,
                    (operation,),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(operation)
        if loaded is None:
            raise CostGovernorError("completion intent clear was lost")
        return loaded

    def record_terminal(
        self,
        decision: CostDecision,
        *,
        evidence_digest: str | None,
    ) -> _CostJournalRecord:
        evidence = (
            None
            if evidence_digest is None
            else _sha256("evidence_digest", evidence_digest)
        )
        terminal_json = _canonical_json_text(decision.as_dict())
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    """
                    SELECT * FROM cost_governor_journal
                    WHERE operation_id = ?
                    """,
                    (decision.operation_id,),
                ).fetchone()
                if row is None:
                    raise CostGovernorError(
                        "terminal cost journal requires active reservation"
                    )
                existing = self._record(row)
                allowed_transition = (
                    existing.state in {"active", "release_pending"}
                    and decision.state == "completed"
                ) or (
                    existing.state == "release_pending"
                    and decision.state == "released_unspent"
                )
                if allowed_transition:
                    conn.execute(
                        """
                        UPDATE cost_governor_journal
                        SET state = ?, terminal_json = ?,
                            evidence_digest = ?
                        WHERE operation_id = ?
                        """,
                        (
                            decision.state,
                            terminal_json,
                            evidence,
                            decision.operation_id,
                        ),
                    )
                elif (
                    existing.state != decision.state
                    or existing.terminal != decision
                    or existing.evidence_digest != evidence
                ):
                    raise CostGovernorConflict(
                        "terminal cost journal replayed with different inputs"
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        loaded = self.load(decision.operation_id)
        if loaded is None:
            raise CostGovernorError("cost journal terminal write was lost")
        return loaded


@dataclass(slots=True)
class _ActiveCostReservation:
    requested_request_digest: str
    receipt: CostReservation
    budget: ResourceBudget


class CostGovernor:
    """Integrated admission/quota governor with declared safe fallback."""

    def __init__(
        self,
        runtime: AdmissionRuntime,
        *,
        journal: _SqliteCostGovernorJournal | None = None,
    ) -> None:
        if not isinstance(runtime, AdmissionRuntime):
            raise TypeError("runtime must be AdmissionRuntime")
        if journal is not None and not isinstance(
            journal,
            _SqliteCostGovernorJournal,
        ):
            raise TypeError("journal must be _SqliteCostGovernorJournal")
        self.runtime = runtime
        self._journal = journal
        self._lock = threading.RLock()
        self._active: dict[str, _ActiveCostReservation] = {}

    @classmethod
    def durable(
        cls,
        path: str | Path,
        *,
        default_tenant_quota: TenantQuota,
        shared_pressure_ledger: SqliteSharedPressureLedger | None = None,
        shared_pressure_scope: str | None = None,
        shared_pressure_owner_id: str | None = None,
    ) -> "CostGovernor":
        if not isinstance(default_tenant_quota, TenantQuota):
            raise TypeError(
                "default_tenant_quota must be TenantQuota"
            )
        ledger = SqliteTenantQuotaLedger(path)
        runtime = AdmissionRuntime(
            quota_ledger=ledger,
            default_tenant_quota=default_tenant_quota,
            shared_pressure_ledger=shared_pressure_ledger,
            shared_pressure_scope=shared_pressure_scope,
            shared_pressure_owner_id=shared_pressure_owner_id,
        )
        return cls(
            runtime,
            journal=_SqliteCostGovernorJournal(path),
        )

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

    @staticmethod
    def _selected_request_for_replay(
        request: AdmissionRequest,
        fallback: SafeCostFallback | None,
        record: _CostJournalRecord,
    ) -> AdmissionRequest:
        receipt = record.reservation
        if receipt.fallback_used:
            if fallback is None:
                raise CostGovernorConflict(
                    "durable fallback reservation requires original fallback"
                )
            if fallback.fallback_id != receipt.fallback_id:
                raise CostGovernorConflict(
                    "durable fallback identity does not match replay"
                )
            selected = CostGovernor._fallback_request(
                request,
                fallback,
            )
        else:
            selected = request

        if (
            selected.capability != receipt.selected_capability
            or _request_digest(selected)
            != receipt.selected_request_digest
        ):
            raise CostGovernorConflict(
                "durable selected request does not match replay"
            )
        return selected

    @staticmethod
    def _lease_from_journal(
        selected: AdmissionRequest,
        record: _CostJournalRecord,
    ) -> AdmissionLease:
        metadata = record.runtime_lease
        if metadata is None:
            raise CostGovernorError(
                "legacy active cost journal lacks runtime lease recovery metadata"
            )
        receipt = record.reservation
        if (
            metadata.lease_id != receipt.lease_id
            or metadata.decision_id != receipt.admission_decision_id
        ):
            raise CostGovernorConflict(
                "runtime lease journal identity does not match reservation receipt"
            )

        remaining = dict(metadata.remaining)
        required_remaining = {
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "wall_seconds",
            "provider_attempts",
            "tool_calls",
            "artifact_bytes",
            "storage_bytes",
            "concurrency",
            "queue_depth",
        }
        if not required_remaining.issubset(remaining):
            raise CostGovernorError(
                "runtime lease journal is missing remaining-budget fields"
            )

        decision = AdmissionDecision(
            decision_id=metadata.decision_id,
            status=AdmissionStatus.ADMIT,
            operation_id=selected.operation_id,
            tenant_id=selected.tenant_id,
            capability=selected.capability,
            reason_code=metadata.reason_code,
            estimated=selected.estimate,
            remaining=remaining,
        )
        return AdmissionLease(
            lease_id=metadata.lease_id,
            decision=decision,
            quota_reservation=record.quota_reservation,
            admitted_at=metadata.admitted_at,
            shared_pressure_lease=metadata.shared_pressure_lease,
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
        persisted: _CostJournalRecord | None = None

        with self._lock:
            current = self._active.get(request.operation_id)
            if current is not None:
                if current.requested_request_digest != requested_digest:
                    raise CostGovernorError(
                        "operation already has a cost reservation with different requested inputs"
                    )
                return current.receipt

            if self._journal is not None:
                persisted = self._journal.load(request.operation_id)
                if persisted is not None:
                    if persisted.requested_request_digest != requested_digest:
                        raise CostGovernorConflict(
                            "durable operation replayed with different requested inputs"
                        )
                    if persisted.state == "release_pending":
                        raise CostGovernorConflict(
                            "operation has release pending recovery"
                        )
                    if persisted.state in {
                        "completed",
                        "released_unspent",
                    }:
                        raise CostGovernorConflict(
                            "operation already has terminal cost journal state"
                        )

                    selected = self._selected_request_for_replay(
                        request,
                        fallback,
                        persisted,
                    )
                    lease = self._lease_from_journal(
                        selected,
                        persisted,
                    )
                    try:
                        self.runtime.reattach(
                            selected,
                            lease,
                            now_wall=now_wall,
                        )
                    except AdmissionRuntimeConflict as exc:
                        raise CostGovernorConflict(str(exc)) from exc
                    except AdmissionRuntimeError as exc:
                        raise CostGovernorError(str(exc)) from exc
                    receipt = persisted.reservation
                    self._active[request.operation_id] = (
                        _ActiveCostReservation(
                            requested_request_digest=requested_digest,
                            receipt=receipt,
                            budget=request.budget,
                        )
                    )
                    return receipt

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

            if self._journal is not None:
                quota_reservation = lease.quota_reservation
                if quota_reservation is None:
                    try:
                        self.runtime.release(lease.operation_id)
                    except Exception:
                        pass
                    raise CostGovernorError(
                        "durable cost governor requires quota reservation"
                    )
                try:
                    self._journal.record_active(
                        requested_request_digest=requested_digest,
                        reservation=receipt,
                        quota_reservation=quota_reservation,
                        runtime_lease=lease,
                    )
                except Exception:
                    if persisted is None:
                        try:
                            self.runtime.release(lease.operation_id)
                        except Exception:
                            pass
                    raise

            self._active[request.operation_id] = _ActiveCostReservation(
                requested_request_digest=requested_digest,
                receipt=receipt,
                budget=request.budget,
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

    def _completed_decision(
        self,
        *,
        operation_id: str,
        receipt: CostReservation,
        quota_reservation: QuotaReservation,
        quota_completion: QuotaCompletion,
        refs: tuple[EvidenceRef, ...],
        operation_overrun_dimensions: tuple[str, ...] = (),
        extra_reasons: tuple[str, ...] = (),
    ) -> CostDecision:
        ledger = self.runtime.quota_ledger
        if ledger is None:
            raise CostGovernorError(
                "cost completion requires quota ledger"
            )
        if quota_reservation.operation_id != operation_id:
            raise CostGovernorConflict(
                "cost journal reservation operation mismatch"
            )
        if quota_completion.operation_id != operation_id:
            raise CostGovernorConflict(
                "cost completion operation mismatch"
            )
        if quota_completion.reservation_id != quota_reservation.reservation_id:
            raise CostGovernorConflict(
                "cost completion reservation mismatch"
            )
        snapshot = ledger.snapshot(quota_completion.tenant_id)
        accounting: BudgetAccountingDecision = qualify_budget_accounting(
            tenant_id=quota_completion.tenant_id,
            operation_id=operation_id,
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
        if operation_overrun_dimensions:
            reasons.append(
                "operation-budget-overrun:"
                + ",".join(operation_overrun_dimensions)
            )
        reasons.extend(extra_reasons)
        normalized = tuple(sorted(set(reasons)))
        return CostDecision(
            operation_id=operation_id,
            tenant_id=quota_completion.tenant_id,
            state="completed",
            reservation_digest=receipt.digest,
            completion_digest=_completion_digest(quota_completion),
            accounting_decision_digest=accounting.decision_digest,
            accepted=not normalized,
            reasons=normalized,
        )

    def _settle_recovered_shared_pressure(
        self,
        record: _CostJournalRecord,
        *,
        now_wall: float | None = None,
    ) -> None:
        metadata = record.runtime_lease
        pressure = (
            None
            if metadata is None
            else metadata.shared_pressure_lease
        )
        if (
            pressure is None
            and self.runtime.shared_pressure_ledger is None
        ):
            return
        try:
            self.runtime.settle_shared_pressure_recovery(
                pressure,
                now_wall=now_wall,
            )
        except AdmissionRuntimeConflict as exc:
            raise CostGovernorConflict(str(exc)) from exc
        except AdmissionRuntimeError as exc:
            raise CostGovernorError(str(exc)) from exc

    def recover_completed(
        self,
        operation_id: str,
        *,
        evidence_refs: Iterable[EvidenceRef],
        now_wall: float | None = None,
    ) -> CostDecision:
        """Recover terminal qualification after a post-completion process loss."""

        operation = _token("operation_id", operation_id)
        refs = _validated_evidence_refs(evidence_refs)
        evidence = _evidence_digest(refs)
        journal = self._journal
        if journal is None:
            raise CostGovernorError(
                "completed recovery requires durable cost journal"
            )

        with self._lock:
            record = journal.load(operation)
            if record is None:
                raise CostGovernorError(
                    "operation has no durable cost journal record"
                )
            if record.state == "released_unspent":
                raise CostGovernorConflict(
                    "released reservation cannot be recovered as completed"
                )
            if record.terminal is not None:
                if record.state != "completed":
                    raise CostGovernorConflict(
                        "terminal cost journal state is inconsistent"
                    )
                if record.evidence_digest != evidence:
                    raise CostGovernorConflict(
                        "completed recovery replayed with different evidence"
                    )
                self._active.pop(operation, None)
                return record.terminal

            ledger = self.runtime.quota_ledger
            if ledger is None:
                raise CostGovernorError(
                    "completed recovery requires quota ledger"
                )
            finder = getattr(ledger, "completion_for_operation", None)
            if not callable(finder):
                raise CostGovernorError(
                    "quota ledger does not support completion recovery"
                )
            try:
                completion = finder(record.tenant_id, operation)
            except QuotaError as exc:
                raise CostGovernorError(
                    "durable completion lookup failed"
                ) from exc

            intent = record.completion_intent
            if intent is not None and intent.evidence_digest != evidence:
                raise CostGovernorConflict(
                    "completed recovery replayed with different evidence"
                )

            if completion is None:
                if intent is None:
                    raise CostGovernorError(
                        "operation has no durable completed accounting"
                    )
                try:
                    completion = ledger.complete(
                        record.quota_reservation.reservation_id,
                        intent.actual,
                    )
                except QuotaConflict as exc:
                    if str(exc).startswith("actual_usage_unknown:"):
                        raise CostGovernorError(str(exc)) from exc
                    raise CostGovernorConflict(str(exc)) from exc
                except QuotaError as exc:
                    raise CostGovernorError(
                        "durable completion recovery failed"
                    ) from exc

            if intent is None:
                overrun_dimensions: tuple[str, ...] = ()
                recovery_reasons = (
                    "operation-budget-recovery-intent-missing",
                )
            else:
                effective_actual = _effective_terminal_actual(
                    intent.actual,
                    completion,
                )
                overrun_dimensions = _budget_overrun_dimensions(
                    intent.budget,
                    effective_actual,
                )
                recovery_reasons = ()

            self._settle_recovered_shared_pressure(
                record,
                now_wall=now_wall,
            )

            decision = self._completed_decision(
                operation_id=operation,
                receipt=record.reservation,
                quota_reservation=record.quota_reservation,
                quota_completion=completion,
                refs=refs,
                operation_overrun_dimensions=overrun_dimensions,
                extra_reasons=recovery_reasons,
            )
            journal.record_terminal(
                decision,
                evidence_digest=evidence,
            )
            self._active.pop(operation, None)
            return decision

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
        evidence = _evidence_digest(refs)
        with self._lock:
            active = self._active.get(operation)
            if active is None:
                raise CostGovernorError(
                    "operation has no active cost reservation"
                )
            journal = self._journal
            if journal is not None:
                journal.record_completion_intent(
                    operation,
                    actual=actual,
                    budget=active.budget,
                    evidence_digest=evidence,
                )
            try:
                completion: AdmissionCompletion = self.runtime.complete(
                    operation,
                    actual,
                    now_wall=now_wall,
                )
            except AdmissionRuntimeConflict as exc:
                if journal is not None:
                    journal.clear_completion_intent(operation)
                raise CostGovernorConflict(str(exc)) from exc
            except AdmissionRuntimeError as exc:
                if journal is not None:
                    journal.clear_completion_intent(operation)
                raise CostGovernorError(str(exc)) from exc
            except ValueError:
                if journal is not None:
                    journal.clear_completion_intent(operation)
                raise

            # The runtime lease is terminal after complete(). From this point on
            # recovery must use the durable journal + quota completion.
            self._active.pop(operation, None)
            try:
                quota_completion = completion.quota_completion
                quota_reservation = completion.lease.quota_reservation
                if quota_completion is None or quota_reservation is None:
                    raise CostGovernorError(
                        "cost completion requires durable quota accounting"
                    )
                decision = self._completed_decision(
                    operation_id=operation,
                    receipt=active.receipt,
                    quota_reservation=quota_reservation,
                    quota_completion=quota_completion,
                    refs=refs,
                    operation_overrun_dimensions=(
                        completion.operation_overrun_dimensions
                    ),
                )
                if journal is not None:
                    journal.record_terminal(
                        decision,
                        evidence_digest=evidence,
                    )
                return decision
            except CostGovernorError:
                raise
            except Exception as exc:
                raise CostGovernorError(
                    "terminal_accounting_qualification_failed"
                ) from exc

    def recover_released(
        self,
        operation_id: str,
        *,
        now_wall: float | None = None,
    ) -> CostDecision:
        """Finish an unspent release interrupted by process loss."""

        operation = _token("operation_id", operation_id)
        journal = self._journal
        if journal is None:
            raise CostGovernorError(
                "release recovery requires durable cost journal"
            )

        with self._lock:
            record = journal.load(operation)
            if record is None:
                raise CostGovernorError(
                    "operation has no durable cost journal record"
                )
            if record.terminal is not None:
                if record.state != "released_unspent":
                    raise CostGovernorConflict(
                        "completed reservation cannot be recovered as released"
                    )
                self._active.pop(operation, None)
                return record.terminal
            if record.state != "release_pending":
                raise CostGovernorConflict(
                    "operation has no release pending recovery"
                )

            ledger = self.runtime.quota_ledger
            if ledger is None:
                raise CostGovernorError(
                    "release recovery requires quota ledger"
                )
            finder = getattr(ledger, "completion_for_operation", None)
            if callable(finder):
                completion = finder(record.tenant_id, operation)
                if completion is not None:
                    raise CostGovernorConflict(
                        "completed accounting cannot be recovered as unspent release"
                    )

            if journal.quota_reservation_exists(
                record.quota_reservation
            ):
                try:
                    ledger.release(
                        record.quota_reservation.reservation_id
                    )
                except QuotaConflict as exc:
                    journal.revert_release_pending(operation)
                    raise CostGovernorConflict(str(exc)) from exc
                except QuotaError as exc:
                    raise CostGovernorError(
                        "durable release recovery failed"
                    ) from exc

            self._settle_recovered_shared_pressure(
                record,
                now_wall=now_wall,
            )

            decision = CostDecision(
                operation_id=operation,
                tenant_id=record.tenant_id,
                state="released_unspent",
                reservation_digest=record.reservation.digest,
                completion_digest=None,
                accounting_decision_digest=None,
                accepted=False,
                reasons=("reservation-released-unspent",),
            )
            journal.record_terminal(
                decision,
                evidence_digest=None,
            )
            self._active.pop(operation, None)
            return decision

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
            journal = self._journal
            if journal is not None:
                journal.mark_release_pending(
                    operation,
                    active.receipt,
                )
            try:
                lease = self.runtime.release(operation)
            except (AdmissionRuntimeConflict, QuotaConflict) as exc:
                if journal is not None:
                    journal.revert_release_pending(operation)
                raise CostGovernorConflict(str(exc)) from exc
            except (AdmissionRuntimeError, QuotaError) as exc:
                if journal is not None:
                    journal.revert_release_pending(operation)
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
            if journal is not None:
                journal.record_terminal(
                    decision,
                    evidence_digest=None,
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
