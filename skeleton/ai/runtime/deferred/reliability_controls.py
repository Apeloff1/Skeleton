"""Reliability controls for VOL-288..292."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PressureLevel(str, Enum):
    NORMAL = "normal"
    HIGH = "high"
    SATURATED = "saturated"


@dataclass(frozen=True, slots=True)
class BufferLimit:
    capacity: int
    high_watermark: int

    def __post_init__(self) -> None:
        if self.capacity <= 0 or not 0 < self.high_watermark <= self.capacity:
            raise ValueError("invalid buffer limits")


@dataclass(frozen=True, slots=True)
class BackpressureSignal:
    depth: int
    limit: BufferLimit
    cancelled: bool = False


@dataclass(frozen=True, slots=True)
class PressureDecision:
    level: PressureLevel
    accept_new: bool
    throttle: bool
    cancelled: bool


def pressure(signal: BackpressureSignal) -> PressureDecision:
    if signal.depth < 0:
        raise ValueError("queue depth must be nonnegative")
    if signal.cancelled:
        return PressureDecision(PressureLevel.SATURATED, False, False, True)
    if signal.depth >= signal.limit.capacity:
        return PressureDecision(PressureLevel.SATURATED, False, True, False)
    if signal.depth >= signal.limit.high_watermark:
        return PressureDecision(PressureLevel.HIGH, True, True, False)
    return PressureDecision(PressureLevel.NORMAL, True, False, False)


class WorkClass(str, Enum):
    OPTIONAL = "optional"
    NORMAL = "normal"
    RECOVERY = "recovery"
    SECURITY = "security"
    AUDIT = "audit"
    AUTHORITY = "authority"


@dataclass(frozen=True, slots=True)
class LoadShedPolicy:
    shed_classes: tuple[WorkClass, ...]


@dataclass(frozen=True, slots=True)
class ShedDecision:
    work_class: WorkClass
    shed: bool
    degraded_response: str | None


def shed(policy: LoadShedPolicy, work_class: WorkClass) -> ShedDecision:
    if len(set(policy.shed_classes)) != len(policy.shed_classes):
        raise ValueError("duplicate shed class")
    protected = {WorkClass.SECURITY, WorkClass.AUDIT, WorkClass.AUTHORITY}
    if work_class in protected:
        return ShedDecision(work_class, False, None)
    yes = work_class in policy.shed_classes
    return ShedDecision(work_class, yes, "overloaded" if yes else None)


@dataclass(frozen=True, slots=True)
class QueueBudget:
    max_depth: int
    max_age: int


@dataclass(frozen=True, slots=True)
class CongestionState:
    depth: int
    oldest_age: int
    service_rate: float


class QueueKind(str, Enum):
    NEW = "new"
    RETRY = "retry"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class QueueDecision:
    kind: QueueKind
    admit: bool
    drain_first: bool
    reason: str


def queue_decision(
    budget: QueueBudget,
    state: CongestionState,
    kind: QueueKind,
) -> QueueDecision:
    if (
        budget.max_depth < 1
        or budget.max_age < 0
        or state.depth < 0
        or state.oldest_age < 0
        or state.service_rate < 0
    ):
        raise ValueError("invalid queue budget/state")
    congested = state.depth >= budget.max_depth or state.oldest_age >= budget.max_age
    if not congested:
        return QueueDecision(kind, True, False, "within budget")
    if kind is QueueKind.RECOVERY:
        return QueueDecision(kind, True, True, "recovery drain")
    return QueueDecision(kind, False, True, "queue budget exceeded")


class FailureClass(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    POLICY = "policy"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RetryBudget:
    budget_id: str
    max_attempts: int
    consumed: int = 0

    def __post_init__(self) -> None:
        if (
            not self.budget_id
            or self.max_attempts < 0
            or not 0 <= self.consumed <= self.max_attempts
        ):
            raise ValueError("invalid retry budget")


@dataclass(frozen=True, slots=True)
class RetryAttempt:
    budget_id: str
    failure: FailureClass
    idempotent: bool


@dataclass(frozen=True, slots=True)
class RetryDecision:
    allowed: bool
    next_budget: RetryBudget
    reason: str


def retry(budget: RetryBudget, attempt: RetryAttempt) -> RetryDecision:
    if not attempt.budget_id:
        return RetryDecision(False, budget, "attempt identity required")
    if attempt.budget_id != budget.budget_id:
        return RetryDecision(False, budget, "budget identity mismatch")
    if attempt.failure is not FailureClass.TRANSIENT:
        return RetryDecision(False, budget, "failure not transient")
    if not attempt.idempotent:
        return RetryDecision(False, budget, "operation not idempotent")
    if budget.consumed >= budget.max_attempts:
        return RetryDecision(False, budget, "budget exhausted")
    return RetryDecision(
        True,
        RetryBudget(budget.budget_id, budget.max_attempts, budget.consumed + 1),
        "retry admitted",
    )


class BreakerState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitBreaker:
    dependency_id: str
    failure_domain: str
    state: BreakerState
    threshold: int
    failures: int


@dataclass(frozen=True, slots=True)
class ProbeResult:
    dependency_id: str
    success: bool


@dataclass(frozen=True, slots=True)
class BreakerDecision:
    state: BreakerState
    allow_primary: bool
    fallback_allowed: bool


def breaker(
    circuit: CircuitBreaker,
    probe: ProbeResult | None = None,
    *,
    fallback_policy_compatible: bool = False,
) -> BreakerDecision:
    if (
        not circuit.dependency_id
        or not circuit.failure_domain
        or circuit.threshold < 1
        or circuit.failures < 0
    ):
        raise ValueError("invalid circuit breaker")
    if probe is not None and not probe.dependency_id:
        raise ValueError("probe identity required")
    if probe is not None and probe.dependency_id != circuit.dependency_id:
        raise ValueError("probe belongs to another dependency")
    if circuit.state is BreakerState.OPEN:
        if probe is None:
            return BreakerDecision(
                BreakerState.OPEN,
                False,
                fallback_policy_compatible,
            )
        return BreakerDecision(
            BreakerState.CLOSED if probe.success else BreakerState.OPEN,
            probe.success,
            fallback_policy_compatible,
        )
    if circuit.failures >= circuit.threshold:
        return BreakerDecision(
            BreakerState.OPEN,
            False,
            fallback_policy_compatible,
        )
    return BreakerDecision(circuit.state, True, False)
