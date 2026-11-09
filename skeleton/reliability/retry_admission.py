"""Connector-neutral retry budgets and SLO-aware admission for VOL-029.

This module is a non-executing reliability decision plane. It standardizes retry
budgets across connector/runtime callers and binds service-level error-budget
state plus accepted capacity evidence into admission decisions.

Unknown external outcomes are never treated as failures. A caller must reconcile
or otherwise prove a known failure before retrying.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import math
import re
from typing import Any

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.distributed.mesh.capacity_qualification import (
    CapacityDisposition,
    CapacityQualificationDecision,
)


RETRY_ADMISSION_SCHEMA_VERSION = 1
RETRY_ADMISSION_TASK_ID = "VOL-029"
RETRY_ADMISSION_ACCOUNTABILITY_ID = "ACC-VOL-029"
_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+#-]{0,191}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RetryAdmissionError(ValueError):
    """Retry/admission input is malformed or violates fail-closed policy."""


class AdmissionKind(str, Enum):
    NEW = "new"
    RETRY = "retry"


class PriorOutcome(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    KNOWN_FAILURE = "known_failure"
    UNKNOWN = "unknown"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise RetryAdmissionError(f"{field} must be a canonical token")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise RetryAdmissionError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RetryAdmissionError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise RetryAdmissionError(f"{field} must be finite numeric")
    return result


def _nonnegative(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0:
        raise RetryAdmissionError(f"{field} must be non-negative")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0:
        raise RetryAdmissionError(f"{field} must be positive")
    return result


def _unit(value: object, field: str) -> float:
    result = _finite(value, field)
    if result < 0.0 or result > 1.0:
        raise RetryAdmissionError(f"{field} must be between 0 and 1")
    return result


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RetryAdmissionError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise RetryAdmissionError(f"{field} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class RetryBudgetPolicy:
    budget_id: str
    max_retries_per_operation: int
    max_retry_tokens: int
    max_retry_fraction: float
    min_error_budget_remaining: float
    max_error_budget_burn_rate: float
    allow_retry_when_degraded: bool = False
    allow_new_when_saturated: bool = False
    schema_version: int = RETRY_ADMISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "budget_id", _token(self.budget_id, "budget_id"))
        object.__setattr__(
            self,
            "max_retries_per_operation",
            _positive_int(self.max_retries_per_operation, "max_retries_per_operation"),
        )
        object.__setattr__(
            self,
            "max_retry_tokens",
            _positive_int(self.max_retry_tokens, "max_retry_tokens"),
        )
        object.__setattr__(
            self,
            "max_retry_fraction",
            _unit(self.max_retry_fraction, "max_retry_fraction"),
        )
        object.__setattr__(
            self,
            "min_error_budget_remaining",
            _unit(self.min_error_budget_remaining, "min_error_budget_remaining"),
        )
        object.__setattr__(
            self,
            "max_error_budget_burn_rate",
            _nonnegative(
                self.max_error_budget_burn_rate,
                "max_error_budget_burn_rate",
            ),
        )
        for field in ("allow_retry_when_degraded", "allow_new_when_saturated"):
            if not isinstance(getattr(self, field), bool):
                raise RetryAdmissionError(f"{field} must be boolean")
        if self.schema_version != RETRY_ADMISSION_SCHEMA_VERSION:
            raise RetryAdmissionError("unsupported retry policy schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": RETRY_ADMISSION_TASK_ID,
            "accountability_id": RETRY_ADMISSION_ACCOUNTABILITY_ID,
            "budget_id": self.budget_id,
            "max_retries_per_operation": self.max_retries_per_operation,
            "max_retry_tokens": self.max_retry_tokens,
            "max_retry_fraction": self.max_retry_fraction,
            "min_error_budget_remaining": self.min_error_budget_remaining,
            "max_error_budget_burn_rate": self.max_error_budget_burn_rate,
            "allow_retry_when_degraded": self.allow_retry_when_degraded,
            "allow_new_when_saturated": self.allow_new_when_saturated,
        }

    @property
    def policy_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class ServiceLevelState:
    service_id: str
    window_id: str
    error_budget_remaining: float
    error_budget_burn_rate: float
    observed_at: float
    max_age_s: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "service_id", _token(self.service_id, "service_id"))
        object.__setattr__(self, "window_id", _token(self.window_id, "window_id"))
        object.__setattr__(
            self,
            "error_budget_remaining",
            _unit(self.error_budget_remaining, "error_budget_remaining"),
        )
        object.__setattr__(
            self,
            "error_budget_burn_rate",
            _nonnegative(self.error_budget_burn_rate, "error_budget_burn_rate"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _nonnegative(self.observed_at, "observed_at"),
        )
        object.__setattr__(self, "max_age_s", _positive(self.max_age_s, "max_age_s"))

    def payload(self) -> dict[str, Any]:
        return {
            "service_id": self.service_id,
            "window_id": self.window_id,
            "error_budget_remaining": self.error_budget_remaining,
            "error_budget_burn_rate": self.error_budget_burn_rate,
            "observed_at": self.observed_at,
            "max_age_s": self.max_age_s,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class RetryBudgetSnapshot:
    policy_digest: str
    service_id: str
    window_id: str
    admitted_requests: int
    admitted_retries: int
    retry_tokens_used: int
    sequence: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_digest",
            _sha(self.policy_digest, "policy_digest"),
        )
        object.__setattr__(self, "service_id", _token(self.service_id, "service_id"))
        object.__setattr__(self, "window_id", _token(self.window_id, "window_id"))
        for field in (
            "admitted_requests",
            "admitted_retries",
            "retry_tokens_used",
            "sequence",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        if self.admitted_retries > self.admitted_requests:
            raise RetryAdmissionError("admitted_retries cannot exceed admitted_requests")
        if self.retry_tokens_used != self.admitted_retries:
            raise RetryAdmissionError("retry token accounting must equal admitted retries")

    def payload(self) -> dict[str, Any]:
        return {
            "policy_digest": self.policy_digest,
            "service_id": self.service_id,
            "window_id": self.window_id,
            "admitted_requests": self.admitted_requests,
            "admitted_retries": self.admitted_retries,
            "retry_tokens_used": self.retry_tokens_used,
            "sequence": self.sequence,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    operation_id: str
    service_id: str
    kind: AdmissionKind | str
    attempt: int
    prior_outcome: PriorOutcome | str
    external_effect: bool
    idempotency_key_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _token(self.operation_id, "operation_id"),
        )
        object.__setattr__(self, "service_id", _token(self.service_id, "service_id"))
        try:
            kind = AdmissionKind(self.kind)
            prior = PriorOutcome(self.prior_outcome)
        except ValueError as exc:
            raise RetryAdmissionError("invalid admission enum") from exc
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "prior_outcome", prior)
        object.__setattr__(self, "attempt", _positive_int(self.attempt, "attempt"))
        if not isinstance(self.external_effect, bool):
            raise RetryAdmissionError("external_effect must be boolean")
        if self.idempotency_key_digest is not None:
            object.__setattr__(
                self,
                "idempotency_key_digest",
                _sha(self.idempotency_key_digest, "idempotency_key_digest"),
            )
        if kind is AdmissionKind.NEW:
            if self.attempt != 1:
                raise RetryAdmissionError("new admission must be attempt 1")
            if prior is not PriorOutcome.NOT_ATTEMPTED:
                raise RetryAdmissionError("new admission cannot have prior outcome")
        else:
            if self.attempt < 2:
                raise RetryAdmissionError("retry admission must be attempt 2 or greater")
            if prior is PriorOutcome.NOT_ATTEMPTED:
                raise RetryAdmissionError("retry admission requires prior outcome")

    def payload(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "service_id": self.service_id,
            "kind": self.kind.value,
            "attempt": self.attempt,
            "prior_outcome": self.prior_outcome.value,
            "external_effect": self.external_effect,
            "idempotency_key_digest": self.idempotency_key_digest,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    admitted: bool
    reasons: tuple[str, ...]
    request_digest: str
    policy_digest: str
    slo_digest: str
    retry_snapshot_digest: str
    capacity_decision_digest: str
    capacity_disposition: CapacityDisposition | str
    projected_retry_fraction: float
    retry_tokens_remaining: int
    authority_scope: str = "reliability-admission-only"
    production_authority: bool = False
    schema_version: int = RETRY_ADMISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.admitted, bool):
            raise RetryAdmissionError("admitted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(reason, str) or not reason for reason in self.reasons
        ):
            raise RetryAdmissionError("reasons must contain non-empty strings")
        for field in (
            "request_digest",
            "policy_digest",
            "slo_digest",
            "retry_snapshot_digest",
            "capacity_decision_digest",
        ):
            object.__setattr__(self, field, _sha(getattr(self, field), field))
        try:
            object.__setattr__(
                self,
                "capacity_disposition",
                CapacityDisposition(self.capacity_disposition),
            )
        except ValueError as exc:
            raise RetryAdmissionError("invalid capacity disposition") from exc
        object.__setattr__(
            self,
            "projected_retry_fraction",
            _unit(self.projected_retry_fraction, "projected_retry_fraction"),
        )
        object.__setattr__(
            self,
            "retry_tokens_remaining",
            _nonnegative_int(self.retry_tokens_remaining, "retry_tokens_remaining"),
        )
        if self.authority_scope != "reliability-admission-only":
            raise RetryAdmissionError("reliability decision scope escalation")
        if self.production_authority is not False:
            raise RetryAdmissionError("reliability decision cannot execute production")
        if self.schema_version != RETRY_ADMISSION_SCHEMA_VERSION:
            raise RetryAdmissionError("unsupported admission decision schema")
        if self.admitted and self.reasons:
            raise RetryAdmissionError("admitted decision cannot carry denial reasons")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": RETRY_ADMISSION_TASK_ID,
            "accountability_id": RETRY_ADMISSION_ACCOUNTABILITY_ID,
            "admitted": self.admitted,
            "reasons": list(self.reasons),
            "request_digest": self.request_digest,
            "policy_digest": self.policy_digest,
            "slo_digest": self.slo_digest,
            "retry_snapshot_digest": self.retry_snapshot_digest,
            "capacity_decision_digest": self.capacity_decision_digest,
            "capacity_disposition": self.capacity_disposition.value,
            "projected_retry_fraction": self.projected_retry_fraction,
            "retry_tokens_remaining": self.retry_tokens_remaining,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def decision_digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.payload())).hexdigest()


def initial_retry_budget(
    *,
    policy: RetryBudgetPolicy,
    service_id: str,
    window_id: str,
) -> RetryBudgetSnapshot:
    if not isinstance(policy, RetryBudgetPolicy):
        raise TypeError("policy must be RetryBudgetPolicy")
    return RetryBudgetSnapshot(
        policy_digest=policy.policy_digest,
        service_id=_token(service_id, "service_id"),
        window_id=_token(window_id, "window_id"),
        admitted_requests=0,
        admitted_retries=0,
        retry_tokens_used=0,
        sequence=0,
    )


def evaluate_admission(
    *,
    policy: RetryBudgetPolicy,
    slo: ServiceLevelState,
    retry_budget: RetryBudgetSnapshot,
    capacity: CapacityQualificationDecision,
    request: AdmissionRequest,
    observed_at: float,
) -> AdmissionDecision:
    if not isinstance(policy, RetryBudgetPolicy):
        raise TypeError("policy must be RetryBudgetPolicy")
    if not isinstance(slo, ServiceLevelState):
        raise TypeError("slo must be ServiceLevelState")
    if not isinstance(retry_budget, RetryBudgetSnapshot):
        raise TypeError("retry_budget must be RetryBudgetSnapshot")
    if not isinstance(capacity, CapacityQualificationDecision):
        raise TypeError("capacity must be CapacityQualificationDecision")
    if not isinstance(request, AdmissionRequest):
        raise TypeError("request must be AdmissionRequest")
    now = _nonnegative(observed_at, "observed_at")

    reasons: list[str] = []
    if retry_budget.policy_digest != policy.policy_digest:
        reasons.append("retry-policy-digest-mismatch")
    if request.service_id != slo.service_id:
        reasons.append("request-slo-service-mismatch")
    if retry_budget.service_id != slo.service_id:
        reasons.append("retry-slo-service-mismatch")
    if retry_budget.window_id != slo.window_id:
        reasons.append("retry-slo-window-mismatch")
    if now < slo.observed_at:
        reasons.append("slo-observation-not-yet-valid")
    if now - slo.observed_at > slo.max_age_s:
        reasons.append("slo-observation-stale")
    if not capacity.accepted:
        reasons.append("capacity-qualification-rejected")
    if slo.error_budget_remaining < policy.min_error_budget_remaining:
        reasons.append(
            "error-budget-retry-closed"
            if request.kind is AdmissionKind.RETRY
            else "error-budget-admission-closed"
        )
    if slo.error_budget_burn_rate > policy.max_error_budget_burn_rate:
        reasons.append("error-budget-burn-rate-exceeded")

    if capacity.disposition is CapacityDisposition.SATURATED:
        if request.kind is AdmissionKind.RETRY:
            reasons.append("capacity-saturated-retry-denied")
        elif not policy.allow_new_when_saturated:
            reasons.append("capacity-saturated-admission-denied")
    elif (
        capacity.disposition is CapacityDisposition.DEGRADED
        and request.kind is AdmissionKind.RETRY
        and not policy.allow_retry_when_degraded
    ):
        reasons.append("capacity-degraded-retry-denied")

    projected_requests = retry_budget.admitted_requests + 1
    projected_retries = retry_budget.admitted_retries
    if request.kind is AdmissionKind.RETRY:
        projected_retries += 1
    projected_retry_fraction = projected_retries / projected_requests

    if request.kind is AdmissionKind.RETRY:
        retry_number = request.attempt - 1
        if retry_number > policy.max_retries_per_operation:
            reasons.append("operation-retry-limit-exceeded")
        if retry_budget.retry_tokens_used >= policy.max_retry_tokens:
            reasons.append("retry-token-budget-exhausted")
        if projected_retry_fraction > policy.max_retry_fraction:
            reasons.append("retry-fraction-budget-exceeded")
        if request.prior_outcome is PriorOutcome.UNKNOWN:
            reasons.append("prior-outcome-unknown-reconciliation-required")
        elif request.prior_outcome is not PriorOutcome.KNOWN_FAILURE:
            reasons.append("retry-prior-outcome-not-failure")
        if request.external_effect and request.idempotency_key_digest is None:
            reasons.append("external-effect-retry-requires-idempotency")

    remaining = max(policy.max_retry_tokens - retry_budget.retry_tokens_used, 0)
    if request.kind is AdmissionKind.RETRY and not reasons:
        remaining -= 1

    normalized = tuple(sorted(set(reasons)))
    return AdmissionDecision(
        admitted=not normalized,
        reasons=normalized,
        request_digest=request.digest,
        policy_digest=policy.policy_digest,
        slo_digest=slo.digest,
        retry_snapshot_digest=retry_budget.digest,
        capacity_decision_digest=capacity.decision_digest,
        capacity_disposition=capacity.disposition,
        projected_retry_fraction=projected_retry_fraction,
        retry_tokens_remaining=remaining,
    )


def consume_admission(
    *,
    snapshot: RetryBudgetSnapshot,
    request: AdmissionRequest,
    decision: AdmissionDecision,
) -> RetryBudgetSnapshot:
    if not isinstance(snapshot, RetryBudgetSnapshot):
        raise TypeError("snapshot must be RetryBudgetSnapshot")
    if not isinstance(request, AdmissionRequest):
        raise TypeError("request must be AdmissionRequest")
    if not isinstance(decision, AdmissionDecision):
        raise TypeError("decision must be AdmissionDecision")
    if not decision.admitted:
        raise RetryAdmissionError("rejected admission cannot consume retry budget")
    if decision.request_digest != request.digest:
        raise RetryAdmissionError("admission decision/request mismatch")
    if decision.retry_snapshot_digest != snapshot.digest:
        raise RetryAdmissionError("admission decision is stale for retry budget")
    if decision.policy_digest != snapshot.policy_digest:
        raise RetryAdmissionError("admission decision/policy mismatch")
    if request.service_id != snapshot.service_id:
        raise RetryAdmissionError("request service mismatch")

    is_retry = request.kind is AdmissionKind.RETRY
    return replace(
        snapshot,
        admitted_requests=snapshot.admitted_requests + 1,
        admitted_retries=snapshot.admitted_retries + (1 if is_retry else 0),
        retry_tokens_used=snapshot.retry_tokens_used + (1 if is_retry else 0),
        sequence=snapshot.sequence + 1,
    )


__all__ = [
    "RETRY_ADMISSION_ACCOUNTABILITY_ID",
    "RETRY_ADMISSION_SCHEMA_VERSION",
    "RETRY_ADMISSION_TASK_ID",
    "AdmissionDecision",
    "AdmissionKind",
    "AdmissionRequest",
    "PriorOutcome",
    "RetryAdmissionError",
    "RetryBudgetPolicy",
    "RetryBudgetSnapshot",
    "ServiceLevelState",
    "consume_admission",
    "evaluate_admission",
    "initial_retry_budget",
]
