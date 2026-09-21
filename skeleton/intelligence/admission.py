"""Deterministic resource-budget admission for expensive AI operations.

Admission is intentionally pure and provider-neutral. It answers one question
before expensive allocation: does the estimated work fit its inherited resource
budget and the current runtime pressure?

The first vertical slice governs provider-facing token/cost/deadline pressure
and generic concurrency/queue/artifact/tool estimates. Quota stores and actual
usage accounting can layer on this receipt without changing the decision shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import math
import time
from typing import Any


class AdmissionError(ValueError):
    """Admission inputs are malformed and cannot be evaluated safely."""


class AdmissionStatus(str, Enum):
    ADMIT = "admit"
    DEFER = "defer"
    REJECT = "reject"


def _finite_nonnegative(value: float | int, *, field: str) -> float:
    if isinstance(value, bool):
        raise AdmissionError(f"{field} must be finite and non-negative")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise AdmissionError(f"{field} must be finite and non-negative")
    return number


def _nonnegative_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AdmissionError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdmissionError(f"{field} must be a positive integer")
    return value


def _identifier(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdmissionError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > 256:
        raise AdmissionError(f"{field} is too long")
    return normalized


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    """Maximum resources one operation is allowed to consume."""

    max_input_tokens: int = 200_000
    max_output_tokens: int = 16_384
    max_cost_usd: float = 10.0
    max_wall_seconds: float = 120.0
    max_provider_attempts: int = 3
    max_tool_calls: int = 32
    max_artifact_bytes: int = 100 * 1024 * 1024
    max_concurrency: int = 32
    max_queue_depth: int = 1_000

    def __post_init__(self) -> None:
        for field_name in (
            "max_input_tokens",
            "max_output_tokens",
            "max_provider_attempts",
            "max_tool_calls",
            "max_artifact_bytes",
            "max_concurrency",
            "max_queue_depth",
        ):
            value = getattr(self, field_name)
            if field_name in {"max_provider_attempts", "max_concurrency"}:
                _positive_int(value, field=field_name)
            else:
                _nonnegative_int(value, field=field_name)
        _finite_nonnegative(self.max_cost_usd, field="max_cost_usd")
        wall = _finite_nonnegative(self.max_wall_seconds, field="max_wall_seconds")
        if wall <= 0:
            raise AdmissionError("max_wall_seconds must be greater than zero")

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_wall_seconds": self.max_wall_seconds,
            "max_provider_attempts": self.max_provider_attempts,
            "max_tool_calls": self.max_tool_calls,
            "max_artifact_bytes": self.max_artifact_bytes,
            "max_concurrency": self.max_concurrency,
            "max_queue_depth": self.max_queue_depth,
        }


@dataclass(frozen=True, slots=True)
class UsageEstimate:
    """Estimated resources before work begins."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    wall_seconds: float = 0.0
    provider_attempts: int = 1
    tool_calls: int = 0
    artifact_bytes: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "input_tokens",
            "output_tokens",
            "provider_attempts",
            "tool_calls",
            "artifact_bytes",
        ):
            value = getattr(self, field_name)
            if field_name == "provider_attempts":
                _positive_int(value, field=field_name)
            else:
                _nonnegative_int(value, field=field_name)
        _finite_nonnegative(self.cost_usd, field="cost_usd")
        _finite_nonnegative(self.wall_seconds, field="wall_seconds")


@dataclass(frozen=True, slots=True)
class RuntimePressure:
    """Current shared pressure observed before admitting this operation."""

    active_operations: int = 0
    queue_depth: int = 0

    def __post_init__(self) -> None:
        _nonnegative_int(self.active_operations, field="active_operations")
        _nonnegative_int(self.queue_depth, field="queue_depth")


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    operation_id: str
    tenant_id: str
    capability: str
    budget: ResourceBudget
    estimate: UsageEstimate
    pressure: RuntimePressure = RuntimePressure()
    priority: int = 50
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        _identifier(self.operation_id, field="operation_id")
        _identifier(self.tenant_id, field="tenant_id")
        _identifier(self.capability, field="capability")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise AdmissionError("priority must be an integer")
        if not 0 <= self.priority <= 100:
            raise AdmissionError("priority must be within [0, 100]")
        if self.deadline_monotonic is not None:
            deadline = float(self.deadline_monotonic)
            if not math.isfinite(deadline):
                raise AdmissionError("deadline_monotonic must be finite")


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    decision_id: str
    status: AdmissionStatus
    operation_id: str
    tenant_id: str
    capability: str
    reason_code: str
    estimated: UsageEstimate
    remaining: dict[str, float | int]

    @property
    def admitted(self) -> bool:
        return self.status is AdmissionStatus.ADMIT

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "status": self.status.value,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "capability": self.capability,
            "reason_code": self.reason_code,
            "remaining": dict(self.remaining),
        }


def _decision_id(request: AdmissionRequest, status: AdmissionStatus, reason: str) -> str:
    material = "\x1f".join(
        (
            request.operation_id,
            request.tenant_id,
            request.capability,
            status.value,
            reason,
            str(request.budget.as_dict()),
            str(request.estimate),
            str(request.pressure),
        )
    ).encode("utf-8")
    return "adm-" + hashlib.sha256(material).hexdigest()[:24]


def _remaining(request: AdmissionRequest) -> dict[str, float | int]:
    budget = request.budget
    estimate = request.estimate
    return {
        "input_tokens": max(0, budget.max_input_tokens - estimate.input_tokens),
        "output_tokens": max(0, budget.max_output_tokens - estimate.output_tokens),
        "cost_usd": max(0.0, budget.max_cost_usd - estimate.cost_usd),
        "wall_seconds": max(0.0, budget.max_wall_seconds - estimate.wall_seconds),
        "provider_attempts": max(
            0, budget.max_provider_attempts - estimate.provider_attempts
        ),
        "tool_calls": max(0, budget.max_tool_calls - estimate.tool_calls),
        "artifact_bytes": max(
            0, budget.max_artifact_bytes - estimate.artifact_bytes
        ),
        "concurrency": max(
            0, budget.max_concurrency - request.pressure.active_operations
        ),
        "queue_depth": max(0, budget.max_queue_depth - request.pressure.queue_depth),
    }


def evaluate_admission(
    request: AdmissionRequest,
    *,
    now_monotonic: float | None = None,
) -> AdmissionDecision:
    """Evaluate a request without mutating quota or runtime state."""

    budget = request.budget
    estimate = request.estimate
    pressure = request.pressure

    checks: tuple[tuple[bool, AdmissionStatus, str], ...] = (
        (
            estimate.input_tokens > budget.max_input_tokens,
            AdmissionStatus.REJECT,
            "input_token_budget_exceeded",
        ),
        (
            estimate.output_tokens > budget.max_output_tokens,
            AdmissionStatus.REJECT,
            "output_token_budget_exceeded",
        ),
        (
            estimate.cost_usd > budget.max_cost_usd,
            AdmissionStatus.REJECT,
            "cost_budget_exceeded",
        ),
        (
            estimate.wall_seconds > budget.max_wall_seconds,
            AdmissionStatus.REJECT,
            "wall_time_budget_exceeded",
        ),
        (
            estimate.provider_attempts > budget.max_provider_attempts,
            AdmissionStatus.REJECT,
            "provider_attempt_budget_exceeded",
        ),
        (
            estimate.tool_calls > budget.max_tool_calls,
            AdmissionStatus.REJECT,
            "tool_call_budget_exceeded",
        ),
        (
            estimate.artifact_bytes > budget.max_artifact_bytes,
            AdmissionStatus.REJECT,
            "artifact_budget_exceeded",
        ),
        (
            pressure.active_operations >= budget.max_concurrency,
            AdmissionStatus.DEFER,
            "concurrency_saturated",
        ),
        (
            pressure.queue_depth >= budget.max_queue_depth,
            AdmissionStatus.REJECT,
            "queue_saturated",
        ),
    )
    status = AdmissionStatus.ADMIT
    reason = "within_budget"
    for failed, candidate_status, candidate_reason in checks:
        if failed:
            status = candidate_status
            reason = candidate_reason
            break

    if status is AdmissionStatus.ADMIT and request.deadline_monotonic is not None:
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        if not math.isfinite(now):
            raise AdmissionError("now_monotonic must be finite")
        remaining_deadline = request.deadline_monotonic - now
        if remaining_deadline <= 0:
            status = AdmissionStatus.REJECT
            reason = "deadline_expired"
        elif estimate.wall_seconds > remaining_deadline:
            status = AdmissionStatus.REJECT
            reason = "estimate_exceeds_deadline"

    return AdmissionDecision(
        decision_id=_decision_id(request, status, reason),
        status=status,
        operation_id=request.operation_id,
        tenant_id=request.tenant_id,
        capability=request.capability,
        reason_code=reason,
        estimated=estimate,
        remaining=_remaining(request),
    )


def require_admission(
    request: AdmissionRequest,
    *,
    now_monotonic: float | None = None,
) -> AdmissionDecision:
    """Return an admission receipt or raise a sanitized admission failure."""

    decision = evaluate_admission(request, now_monotonic=now_monotonic)
    if not decision.admitted:
        raise AdmissionError(decision.reason_code)
    return decision


__all__ = [
    "AdmissionDecision",
    "AdmissionError",
    "AdmissionRequest",
    "AdmissionStatus",
    "ResourceBudget",
    "RuntimePressure",
    "UsageEstimate",
    "evaluate_admission",
    "require_admission",
]
