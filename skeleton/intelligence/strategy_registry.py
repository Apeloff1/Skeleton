"""Versioned reasoning/search strategy and stopping policy for P1-INTEL-03.

This module is a deterministic control-plane contract. It does not perform
reasoning or provider calls. Existing cognitive runtimes execute work; this
registry makes strategy choice, uncertainty, budgets, value-of-information and
termination mechanically explicit so no search loop relies on model prose to
decide whether it may continue.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

from skeleton.contracts.canonical import EvidenceRef


REASONING_POLICY_SCHEMA_VERSION = 1
REASONING_POLICY_TASK_ID = "P1-INTEL-03"
REASONING_POLICY_ACCOUNTABILITY_ID = "ACC-P1-INTEL-03"
_MAX_STRATEGIES = 32
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ReasoningPolicyError(ValueError):
    """Reasoning policy or observation is malformed."""


class ReasoningStrategy(str, Enum):
    DIRECT = "direct"
    RETRIEVE = "retrieve"
    DECOMPOSE = "decompose"
    SEARCH = "search"
    VERIFY = "verify"
    REFLECT = "reflect"
    CRITIQUE = "critique"
    REPAIR = "repair"


class StopDisposition(str, Enum):
    CONTINUE = "continue"
    COMPLETE = "complete"
    ABSTAIN = "abstain"
    ESCALATE = "escalate"
    BUDGET_EXHAUSTED = "budget_exhausted"
    VALUE_EXHAUSTED = "value_exhausted"
    STALLED = "stalled"
    DEADLINE = "deadline"


class ReasoningRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise ReasoningPolicyError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, max_length: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReasoningPolicyError(f"{field} must be non-empty")
    normalized = value.strip()
    if value != normalized or len(normalized) > max_length:
        raise ReasoningPolicyError(f"{field} must be normalized")
    return normalized


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReasoningPolicyError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReasoningPolicyError(f"{field} must be a non-negative integer")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReasoningPolicyError(f"{field} must be finite numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ReasoningPolicyError(f"{field} must be finite numeric")
    return number


def _unit(value: object, field: str) -> float:
    number = _finite(value, field)
    if not 0.0 <= number <= 1.0:
        raise ReasoningPolicyError(f"{field} must be in [0, 1]")
    return number


def _positive(value: object, field: str) -> float:
    number = _finite(value, field)
    if number <= 0.0:
        raise ReasoningPolicyError(f"{field} must be positive")
    return number


def _nonnegative(value: object, field: str) -> float:
    number = _finite(value, field)
    if number < 0.0:
        raise ReasoningPolicyError(f"{field} must be non-negative")
    return number


def _canonical_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ReasoningPolicy:
    policy_id: str
    version: int
    allowed_strategies: tuple[ReasoningStrategy, ...]
    default_strategy: ReasoningStrategy
    max_steps: int
    max_tokens: int
    max_cost_units: float
    max_wall_time_s: float
    min_value_of_information: float
    completion_confidence: float
    max_uncertainty: float
    max_stall_steps: int
    require_verification_for_high_risk: bool = True
    schema_version: int = REASONING_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _token(self.policy_id, "policy_id"))
        object.__setattr__(self, "version", _positive_int(self.version, "version"))
        if (
            not isinstance(self.allowed_strategies, tuple)
            or not self.allowed_strategies
            or len(self.allowed_strategies) > _MAX_STRATEGIES
        ):
            raise ReasoningPolicyError(
                "allowed_strategies must be a bounded non-empty tuple"
            )
        normalized: list[ReasoningStrategy] = []
        for value in self.allowed_strategies:
            try:
                strategy = ReasoningStrategy(value)
            except ValueError as exc:
                raise ReasoningPolicyError(
                    "allowed_strategies contains invalid strategy"
                ) from exc
            if strategy not in normalized:
                normalized.append(strategy)
        if len(normalized) != len(self.allowed_strategies):
            raise ReasoningPolicyError("allowed_strategies must be unique")
        object.__setattr__(self, "allowed_strategies", tuple(normalized))
        try:
            default = ReasoningStrategy(self.default_strategy)
        except ValueError as exc:
            raise ReasoningPolicyError("default_strategy is invalid") from exc
        if default not in normalized:
            raise ReasoningPolicyError(
                "default_strategy must be allowed by the policy"
            )
        object.__setattr__(self, "default_strategy", default)
        object.__setattr__(self, "max_steps", _positive_int(self.max_steps, "max_steps"))
        object.__setattr__(self, "max_tokens", _positive_int(self.max_tokens, "max_tokens"))
        object.__setattr__(
            self,
            "max_cost_units",
            _positive(self.max_cost_units, "max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_wall_time_s",
            _positive(self.max_wall_time_s, "max_wall_time_s"),
        )
        object.__setattr__(
            self,
            "min_value_of_information",
            _unit(self.min_value_of_information, "min_value_of_information"),
        )
        object.__setattr__(
            self,
            "completion_confidence",
            _unit(self.completion_confidence, "completion_confidence"),
        )
        object.__setattr__(
            self,
            "max_uncertainty",
            _unit(self.max_uncertainty, "max_uncertainty"),
        )
        object.__setattr__(
            self,
            "max_stall_steps",
            _positive_int(self.max_stall_steps, "max_stall_steps"),
        )
        if self.max_stall_steps < 2:
            raise ReasoningPolicyError(
                "max_stall_steps must be at least two"
            )
        if self.max_stall_steps > self.max_steps:
            raise ReasoningPolicyError(
                "max_stall_steps cannot exceed max_steps"
            )
        if not isinstance(self.require_verification_for_high_risk, bool):
            raise ReasoningPolicyError(
                "require_verification_for_high_risk must be boolean"
            )
        if self.require_verification_for_high_risk is not True:
            raise ReasoningPolicyError(
                "high-risk verification cannot be disabled"
            )
        if self.schema_version != REASONING_POLICY_SCHEMA_VERSION:
            raise ReasoningPolicyError("unsupported policy schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "allowed_strategies": [item.value for item in self.allowed_strategies],
            "default_strategy": self.default_strategy.value,
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
            "min_value_of_information": self.min_value_of_information,
            "completion_confidence": self.completion_confidence,
            "max_uncertainty": self.max_uncertainty,
            "max_stall_steps": self.max_stall_steps,
            "require_verification_for_high_risk": self.require_verification_for_high_risk,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class StrategyCandidate:
    strategy: ReasoningStrategy
    expected_quality: float
    expected_uncertainty_reduction: float
    expected_cost_units: float
    expected_tokens: int
    expected_wall_time_s: float
    verification_capable: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "strategy",
                ReasoningStrategy(self.strategy),
            )
        except ValueError as exc:
            raise ReasoningPolicyError("strategy is invalid") from exc
        object.__setattr__(
            self,
            "expected_quality",
            _unit(self.expected_quality, "expected_quality"),
        )
        object.__setattr__(
            self,
            "expected_uncertainty_reduction",
            _unit(
                self.expected_uncertainty_reduction,
                "expected_uncertainty_reduction",
            ),
        )
        object.__setattr__(
            self,
            "expected_cost_units",
            _nonnegative(self.expected_cost_units, "expected_cost_units"),
        )
        object.__setattr__(
            self,
            "expected_tokens",
            _nonnegative_int(self.expected_tokens, "expected_tokens"),
        )
        object.__setattr__(
            self,
            "expected_wall_time_s",
            _nonnegative(self.expected_wall_time_s, "expected_wall_time_s"),
        )
        if not isinstance(self.verification_capable, bool):
            raise ReasoningPolicyError("verification_capable must be boolean")

    def payload(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "expected_quality": self.expected_quality,
            "expected_uncertainty_reduction": self.expected_uncertainty_reduction,
            "expected_cost_units": self.expected_cost_units,
            "expected_tokens": self.expected_tokens,
            "expected_wall_time_s": self.expected_wall_time_s,
            "verification_capable": self.verification_capable,
        }


@dataclass(frozen=True, slots=True)
class StrategySelection:
    strategy: ReasoningStrategy
    policy_digest: str
    candidates_digest: str
    reason: str
    score: float

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "strategy",
                ReasoningStrategy(self.strategy),
            )
        except ValueError as exc:
            raise ReasoningPolicyError("selection strategy is invalid") from exc
        for field in ("policy_digest", "candidates_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ReasoningPolicyError(f"{field} must be lowercase sha256")
        if not isinstance(self.reason, str) or not self.reason:
            raise ReasoningPolicyError("selection reason must be non-empty")
        object.__setattr__(self, "score", _finite(self.score, "selection score"))

    def payload(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "policy_digest": self.policy_digest,
            "candidates_digest": self.candidates_digest,
            "reason": self.reason,
            "score": self.score,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class ReasoningStep:
    step_index: int
    cumulative_tokens: int
    cumulative_cost_units: float
    elapsed_s: float
    confidence: float
    uncertainty: float
    value_of_information: float
    progress_digest: str
    verification_passed: bool = False
    explicit_stop: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "step_index",
            _positive_int(self.step_index, "step_index"),
        )
        object.__setattr__(
            self,
            "cumulative_tokens",
            _nonnegative_int(self.cumulative_tokens, "cumulative_tokens"),
        )
        object.__setattr__(
            self,
            "cumulative_cost_units",
            _nonnegative(self.cumulative_cost_units, "cumulative_cost_units"),
        )
        object.__setattr__(
            self,
            "elapsed_s",
            _nonnegative(self.elapsed_s, "elapsed_s"),
        )
        object.__setattr__(
            self,
            "confidence",
            _unit(self.confidence, "confidence"),
        )
        object.__setattr__(
            self,
            "uncertainty",
            _unit(self.uncertainty, "uncertainty"),
        )
        object.__setattr__(
            self,
            "value_of_information",
            _unit(self.value_of_information, "value_of_information"),
        )
        if (
            not isinstance(self.progress_digest, str)
            or len(self.progress_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.progress_digest)
        ):
            raise ReasoningPolicyError(
                "progress_digest must be lowercase sha256"
            )
        if not isinstance(self.verification_passed, bool):
            raise ReasoningPolicyError("verification_passed must be boolean")
        if not isinstance(self.explicit_stop, bool):
            raise ReasoningPolicyError("explicit_stop must be boolean")

    def payload(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "cumulative_tokens": self.cumulative_tokens,
            "cumulative_cost_units": self.cumulative_cost_units,
            "elapsed_s": self.elapsed_s,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "value_of_information": self.value_of_information,
            "progress_digest": self.progress_digest,
            "verification_passed": self.verification_passed,
            "explicit_stop": self.explicit_stop,
        }


@dataclass(frozen=True, slots=True)
class StoppingDecision:
    disposition: StopDisposition
    reason: str
    policy_digest: str
    history_digest: str
    steps_remaining: int
    tokens_remaining: int
    cost_remaining: float
    time_remaining_s: float
    task_id: str = REASONING_POLICY_TASK_ID
    accountability_id: str = REASONING_POLICY_ACCOUNTABILITY_ID
    schema_version: int = REASONING_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "disposition",
                StopDisposition(self.disposition),
            )
        except ValueError as exc:
            raise ReasoningPolicyError("stop disposition is invalid") from exc
        if not isinstance(self.reason, str) or not self.reason:
            raise ReasoningPolicyError("stop reason must be non-empty")
        for field in ("policy_digest", "history_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ReasoningPolicyError(f"{field} must be lowercase sha256")
        object.__setattr__(
            self,
            "steps_remaining",
            _nonnegative_int(self.steps_remaining, "steps_remaining"),
        )
        object.__setattr__(
            self,
            "tokens_remaining",
            _nonnegative_int(self.tokens_remaining, "tokens_remaining"),
        )
        object.__setattr__(
            self,
            "cost_remaining",
            _nonnegative(self.cost_remaining, "cost_remaining"),
        )
        object.__setattr__(
            self,
            "time_remaining_s",
            _nonnegative(self.time_remaining_s, "time_remaining_s"),
        )
        if self.task_id != REASONING_POLICY_TASK_ID:
            raise ReasoningPolicyError("task_id drift")
        if self.accountability_id != REASONING_POLICY_ACCOUNTABILITY_ID:
            raise ReasoningPolicyError("accountability_id drift")
        if self.schema_version != REASONING_POLICY_SCHEMA_VERSION:
            raise ReasoningPolicyError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "disposition": self.disposition.value,
            "reason": self.reason,
            "policy_digest": self.policy_digest,
            "history_digest": self.history_digest,
            "steps_remaining": self.steps_remaining,
            "tokens_remaining": self.tokens_remaining,
            "cost_remaining": self.cost_remaining,
            "time_remaining_s": self.time_remaining_s,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def evidence_ref(
        self,
        *,
        source: str = "p1:intel-03:reasoning-stop-policy",
    ) -> EvidenceRef:
        if self.disposition is StopDisposition.CONTINUE:
            raise ReasoningPolicyError(
                "continue decision is not terminal promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source"),
            digest=self.decision_digest,
            category="reasoning_stop_policy",
        )



@dataclass(frozen=True, slots=True)
class ReasoningBudgetSnapshot:
    """Replay-stable view of consumed and residual cognitive budget."""

    policy_digest: str
    history_digest: str
    steps_used: int
    tokens_used: int
    cost_used: float
    time_used_s: float
    steps_remaining: int
    tokens_remaining: int
    cost_remaining: float
    time_remaining_s: float

    def __post_init__(self) -> None:
        for field in ("policy_digest", "history_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ReasoningPolicyError(f"{field} must be lowercase sha256")
        for field in (
            "steps_used",
            "tokens_used",
            "steps_remaining",
            "tokens_remaining",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative_int(getattr(self, field), field),
            )
        for field in (
            "cost_used",
            "time_used_s",
            "cost_remaining",
            "time_remaining_s",
        ):
            object.__setattr__(
                self,
                field,
                _nonnegative(getattr(self, field), field),
            )

    @property
    def exhausted(self) -> bool:
        return (
            self.steps_remaining == 0
            or self.tokens_remaining == 0
            or self.cost_remaining <= 0.0
            or self.time_remaining_s <= 0.0
        )

    def payload(self) -> dict[str, Any]:
        return {
            "policy_digest": self.policy_digest,
            "history_digest": self.history_digest,
            "steps_used": self.steps_used,
            "tokens_used": self.tokens_used,
            "cost_used": self.cost_used,
            "time_used_s": self.time_used_s,
            "steps_remaining": self.steps_remaining,
            "tokens_remaining": self.tokens_remaining,
            "cost_remaining": self.cost_remaining,
            "time_remaining_s": self.time_remaining_s,
            "exhausted": self.exhausted,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class StrategyReservation:
    """Hard residual-budget envelope for one selected cognitive strategy."""

    strategy: ReasoningStrategy
    policy_digest: str
    history_digest: str
    selection_digest: str
    expected_tokens: int
    expected_cost_units: float
    expected_wall_time_s: float
    token_ceiling: int
    cost_ceiling: float
    time_ceiling_s: float

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "strategy", ReasoningStrategy(self.strategy))
        except ValueError as exc:
            raise ReasoningPolicyError("reservation strategy is invalid") from exc
        for field in ("policy_digest", "history_digest", "selection_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ReasoningPolicyError(f"{field} must be lowercase sha256")
        object.__setattr__(
            self,
            "expected_tokens",
            _nonnegative_int(self.expected_tokens, "expected_tokens"),
        )
        object.__setattr__(
            self,
            "expected_cost_units",
            _nonnegative(self.expected_cost_units, "expected_cost_units"),
        )
        object.__setattr__(
            self,
            "expected_wall_time_s",
            _nonnegative(self.expected_wall_time_s, "expected_wall_time_s"),
        )
        object.__setattr__(
            self,
            "token_ceiling",
            _nonnegative_int(self.token_ceiling, "token_ceiling"),
        )
        object.__setattr__(
            self,
            "cost_ceiling",
            _nonnegative(self.cost_ceiling, "cost_ceiling"),
        )
        object.__setattr__(
            self,
            "time_ceiling_s",
            _nonnegative(self.time_ceiling_s, "time_ceiling_s"),
        )
        if self.expected_tokens > self.token_ceiling:
            raise ReasoningPolicyError("expected tokens exceed reservation ceiling")
        if self.expected_cost_units > self.cost_ceiling:
            raise ReasoningPolicyError("expected cost exceeds reservation ceiling")
        if self.expected_wall_time_s > self.time_ceiling_s:
            raise ReasoningPolicyError("expected wall time exceeds reservation ceiling")

    def payload(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy.value,
            "policy_digest": self.policy_digest,
            "history_digest": self.history_digest,
            "selection_digest": self.selection_digest,
            "expected_tokens": self.expected_tokens,
            "expected_cost_units": self.expected_cost_units,
            "expected_wall_time_s": self.expected_wall_time_s,
            "token_ceiling": self.token_ceiling,
            "cost_ceiling": self.cost_ceiling,
            "time_ceiling_s": self.time_ceiling_s,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class CognitiveControlDecision:
    """One hash-chainable metacognitive control decision.

    The object records only structured policy state, not hidden reasoning text.
    A continuing decision must carry both a strategy selection and a hard
    reservation bounded by the residual policy envelope.
    """

    decision_index: int
    risk: ReasoningRisk
    stopping: StoppingDecision
    candidates_digest: str
    previous_decision_digest: str
    selection: StrategySelection | None = None
    reservation: StrategyReservation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_index",
            _positive_int(self.decision_index, "decision_index"),
        )
        try:
            object.__setattr__(self, "risk", ReasoningRisk(self.risk))
        except ValueError as exc:
            raise ReasoningPolicyError("control decision risk is invalid") from exc
        if not isinstance(self.stopping, StoppingDecision):
            raise ReasoningPolicyError("stopping must be StoppingDecision")
        for field in ("candidates_digest", "previous_decision_digest"):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ReasoningPolicyError(f"{field} must be lowercase sha256")
        continuing = self.stopping.disposition is StopDisposition.CONTINUE
        if continuing:
            if not isinstance(self.selection, StrategySelection):
                raise ReasoningPolicyError(
                    "continuing decision requires strategy selection"
                )
            if not isinstance(self.reservation, StrategyReservation):
                raise ReasoningPolicyError(
                    "continuing decision requires strategy reservation"
                )
            if self.selection.policy_digest != self.stopping.policy_digest:
                raise ReasoningPolicyError("selection policy identity drift")
            if self.selection.candidates_digest != self.candidates_digest:
                raise ReasoningPolicyError("candidate identity drift")
            if self.reservation.policy_digest != self.stopping.policy_digest:
                raise ReasoningPolicyError("reservation policy identity drift")
            if self.reservation.history_digest != self.stopping.history_digest:
                raise ReasoningPolicyError("reservation history identity drift")
            if self.reservation.selection_digest != self.selection.digest:
                raise ReasoningPolicyError("reservation selection identity drift")
            if self.reservation.strategy is not self.selection.strategy:
                raise ReasoningPolicyError("reservation strategy drift")
        elif self.selection is not None or self.reservation is not None:
            raise ReasoningPolicyError(
                "terminal decision cannot reserve another reasoning step"
            )

    def payload(self) -> dict[str, Any]:
        return {
            "decision_index": self.decision_index,
            "risk": self.risk.value,
            "stopping": self.stopping.payload(),
            "candidates_digest": self.candidates_digest,
            "previous_decision_digest": self.previous_decision_digest,
            "selection": self.selection.payload() if self.selection else None,
            "reservation": self.reservation.payload() if self.reservation else None,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())


def _validate_reasoning_history(
    rows: tuple[ReasoningStep, ...],
    *,
    require_nonempty: bool,
) -> None:
    if require_nonempty and not rows:
        raise ReasoningPolicyError(
            "history must contain at least one ReasoningStep"
        )
    if any(not isinstance(row, ReasoningStep) for row in rows):
        raise ReasoningPolicyError("history contains non-ReasoningStep value")
    expected_indices = tuple(range(1, len(rows) + 1))
    if tuple(row.step_index for row in rows) != expected_indices:
        raise ReasoningPolicyError(
            "reasoning history step indices must be contiguous from one"
        )

    previous_tokens = -1
    previous_cost = -1.0
    previous_elapsed = -1.0
    for row in rows:
        if row.cumulative_tokens < previous_tokens:
            raise ReasoningPolicyError("cumulative_tokens cannot decrease")
        if row.cumulative_cost_units < previous_cost:
            raise ReasoningPolicyError("cumulative_cost_units cannot decrease")
        if row.elapsed_s < previous_elapsed:
            raise ReasoningPolicyError("elapsed_s cannot decrease")
        previous_tokens = row.cumulative_tokens
        previous_cost = row.cumulative_cost_units
        previous_elapsed = row.elapsed_s


def reasoning_budget_snapshot(
    policy: ReasoningPolicy,
    history: Iterable[ReasoningStep] = (),
) -> ReasoningBudgetSnapshot:
    """Compute a deterministic residual budget from cumulative step history."""

    if not isinstance(policy, ReasoningPolicy):
        raise TypeError("policy must be ReasoningPolicy")
    rows = tuple(history)
    _validate_reasoning_history(rows, require_nonempty=False)
    latest = rows[-1] if rows else None
    steps_used = latest.step_index if latest else 0
    tokens_used = latest.cumulative_tokens if latest else 0
    cost_used = latest.cumulative_cost_units if latest else 0.0
    time_used = latest.elapsed_s if latest else 0.0
    return ReasoningBudgetSnapshot(
        policy_digest=policy.digest,
        history_digest=_canonical_digest([row.payload() for row in rows]),
        steps_used=steps_used,
        tokens_used=tokens_used,
        cost_used=round(cost_used, 8),
        time_used_s=round(time_used, 8),
        steps_remaining=max(0, policy.max_steps - steps_used),
        tokens_remaining=max(0, policy.max_tokens - tokens_used),
        cost_remaining=round(max(0.0, policy.max_cost_units - cost_used), 8),
        time_remaining_s=round(max(0.0, policy.max_wall_time_s - time_used), 8),
    )


def _candidate_digest(rows: Iterable[StrategyCandidate]) -> str:
    ordered = sorted(tuple(rows), key=lambda item: item.strategy.value)
    return _canonical_digest([row.payload() for row in ordered])


def evaluate_cognitive_control(
    policy: ReasoningPolicy,
    candidates: Iterable[StrategyCandidate],
    history: Iterable[ReasoningStep],
    *,
    risk: ReasoningRisk,
    decision_index: int = 1,
    previous_decision_digest: str = "0" * 64,
) -> CognitiveControlDecision:
    """Atomically decide whether to stop or reserve one bounded next step."""

    rows = tuple(history)
    candidate_rows = tuple(candidates)
    if any(not isinstance(row, StrategyCandidate) for row in candidate_rows):
        raise ReasoningPolicyError(
            "candidates must contain StrategyCandidate values"
        )
    if len({row.strategy for row in candidate_rows}) != len(candidate_rows):
        raise ReasoningPolicyError("strategy candidates must be unique")
    candidates_digest = _candidate_digest(candidate_rows)
    stopping = evaluate_stopping(policy, rows, risk=risk)

    if stopping.disposition is not StopDisposition.CONTINUE:
        return CognitiveControlDecision(
            decision_index=decision_index,
            risk=risk,
            stopping=stopping,
            candidates_digest=candidates_digest,
            previous_decision_digest=previous_decision_digest,
        )

    budget = reasoning_budget_snapshot(policy, rows)
    try:
        selection = select_strategy(
            policy,
            candidate_rows,
            risk=risk,
            history=rows,
        )
    except ReasoningPolicyError as exc:
        if str(exc) != "no admissible reasoning strategy":
            raise
        stopping = StoppingDecision(
            disposition=StopDisposition.BUDGET_EXHAUSTED,
            reason="no-admissible-strategy-fits-residual-budget",
            policy_digest=policy.digest,
            history_digest=budget.history_digest,
            steps_remaining=budget.steps_remaining,
            tokens_remaining=budget.tokens_remaining,
            cost_remaining=budget.cost_remaining,
            time_remaining_s=budget.time_remaining_s,
        )
        return CognitiveControlDecision(
            decision_index=decision_index,
            risk=risk,
            stopping=stopping,
            candidates_digest=candidates_digest,
            previous_decision_digest=previous_decision_digest,
        )

    selected = next(
        row for row in candidate_rows if row.strategy is selection.strategy
    )
    reservation = StrategyReservation(
        strategy=selection.strategy,
        policy_digest=policy.digest,
        history_digest=budget.history_digest,
        selection_digest=selection.digest,
        expected_tokens=selected.expected_tokens,
        expected_cost_units=selected.expected_cost_units,
        expected_wall_time_s=selected.expected_wall_time_s,
        token_ceiling=budget.tokens_remaining,
        cost_ceiling=budget.cost_remaining,
        time_ceiling_s=budget.time_remaining_s,
    )
    return CognitiveControlDecision(
        decision_index=decision_index,
        risk=risk,
        stopping=stopping,
        candidates_digest=candidates_digest,
        previous_decision_digest=previous_decision_digest,
        selection=selection,
        reservation=reservation,
    )


def verify_cognitive_control_chain(
    decisions: Iterable[CognitiveControlDecision],
) -> bool:
    """Verify decision ordering, hash linkage and terminal finality."""

    rows = tuple(decisions)
    if not rows:
        return False
    previous = "0" * 64
    terminal_seen = False
    policy_digest: str | None = None
    for expected_index, decision in enumerate(rows, start=1):
        if not isinstance(decision, CognitiveControlDecision):
            return False
        if decision.decision_index != expected_index:
            return False
        if decision.previous_decision_digest != previous:
            return False
        if terminal_seen:
            return False
        current_policy = decision.stopping.policy_digest
        if policy_digest is None:
            policy_digest = current_policy
        elif current_policy != policy_digest:
            return False
        if decision.stopping.disposition is not StopDisposition.CONTINUE:
            terminal_seen = True
        previous = decision.decision_digest
    return True


class ReasoningPolicyRegistry:
    """Versioned immutable-by-key policy registry."""

    def __init__(self) -> None:
        self._policies: dict[tuple[str, int], ReasoningPolicy] = {}

    def register(self, policy: ReasoningPolicy) -> None:
        if not isinstance(policy, ReasoningPolicy):
            raise TypeError("policy must be ReasoningPolicy")
        key = (policy.policy_id, policy.version)
        existing = self._policies.get(key)
        if existing is not None and existing.digest != policy.digest:
            raise ReasoningPolicyError(
                "policy version is immutable once registered"
            )
        self._policies[key] = policy

    def get(self, policy_id: str, version: int) -> ReasoningPolicy:
        key = (_token(policy_id, "policy_id"), _positive_int(version, "version"))
        try:
            return self._policies[key]
        except KeyError as exc:
            raise KeyError(f"unknown reasoning policy {key[0]}:{key[1]}") from exc

    def latest(self, policy_id: str) -> ReasoningPolicy:
        resolved = _token(policy_id, "policy_id")
        matches = [
            policy
            for (candidate_id, _), policy in self._policies.items()
            if candidate_id == resolved
        ]
        if not matches:
            raise KeyError(f"unknown reasoning policy {resolved}")
        return max(matches, key=lambda item: item.version)

    def snapshot(self) -> dict[str, Any]:
        rows = [
            policy.payload()
            for _, policy in sorted(
                self._policies.items(),
                key=lambda item: item[0],
            )
        ]
        return {
            "schema_version": REASONING_POLICY_SCHEMA_VERSION,
            "policies": rows,
            "digest": _canonical_digest(rows),
        }


def select_strategy(
    policy: ReasoningPolicy,
    candidates: Iterable[StrategyCandidate],
    *,
    risk: ReasoningRisk,
    history: Iterable[ReasoningStep] | None = None,
) -> StrategySelection:
    """Choose the best admissible strategy deterministically."""

    if not isinstance(policy, ReasoningPolicy):
        raise TypeError("policy must be ReasoningPolicy")
    try:
        resolved_risk = ReasoningRisk(risk)
    except ValueError as exc:
        raise ReasoningPolicyError("risk is invalid") from exc
    rows = tuple(candidates)
    if not rows or any(not isinstance(row, StrategyCandidate) for row in rows):
        raise ReasoningPolicyError(
            "candidates must contain StrategyCandidate values"
        )
    if len({row.strategy for row in rows}) != len(rows):
        raise ReasoningPolicyError("strategy candidates must be unique")

    require_verification = (
        policy.require_verification_for_high_risk
        and resolved_risk in {ReasoningRisk.HIGH, ReasoningRisk.CRITICAL}
    )
    budget = (
        reasoning_budget_snapshot(policy, ())
        if history is None
        else reasoning_budget_snapshot(policy, history)
    )
    if budget.steps_remaining == 0:
        raise ReasoningPolicyError("no admissible reasoning strategy")
    admissible: list[StrategyCandidate] = []
    for row in rows:
        if row.strategy not in policy.allowed_strategies:
            continue
        if row.expected_tokens > budget.tokens_remaining:
            continue
        if row.expected_cost_units > budget.cost_remaining:
            continue
        if row.expected_wall_time_s > budget.time_remaining_s:
            continue
        if require_verification and not row.verification_capable:
            continue
        admissible.append(row)

    if not admissible:
        raise ReasoningPolicyError("no admissible reasoning strategy")

    def score(row: StrategyCandidate) -> float:
        token_pressure = row.expected_tokens / policy.max_tokens
        cost_pressure = row.expected_cost_units / policy.max_cost_units
        time_pressure = row.expected_wall_time_s / policy.max_wall_time_s
        return round(
            0.55 * row.expected_quality
            + 0.25 * row.expected_uncertainty_reduction
            - 0.08 * token_pressure
            - 0.07 * cost_pressure
            - 0.05 * time_pressure,
            8,
        )

    selected = sorted(
        admissible,
        key=lambda row: (-score(row), row.strategy.value),
    )[0]
    payload = [row.payload() for row in sorted(rows, key=lambda item: item.strategy.value)]
    return StrategySelection(
        strategy=selected.strategy,
        policy_digest=policy.digest,
        candidates_digest=_canonical_digest(payload),
        reason=(
            "highest-admissible-quality-value-under-bounded-cost"
            + ("-with-verification" if require_verification else "")
        ),
        score=score(selected),
    )


def evaluate_stopping(
    policy: ReasoningPolicy,
    history: Iterable[ReasoningStep],
    *,
    risk: ReasoningRisk,
) -> StoppingDecision:
    """Return a deterministic bounded continuation/stop decision."""

    if not isinstance(policy, ReasoningPolicy):
        raise TypeError("policy must be ReasoningPolicy")
    try:
        resolved_risk = ReasoningRisk(risk)
    except ValueError as exc:
        raise ReasoningPolicyError("risk is invalid") from exc
    rows = tuple(history)
    _validate_reasoning_history(rows, require_nonempty=True)

    latest = rows[-1]
    steps_remaining = max(0, policy.max_steps - latest.step_index)
    tokens_remaining = max(0, policy.max_tokens - latest.cumulative_tokens)
    cost_remaining = max(0.0, policy.max_cost_units - latest.cumulative_cost_units)
    time_remaining = max(0.0, policy.max_wall_time_s - latest.elapsed_s)
    history_digest = _canonical_digest([row.payload() for row in rows])

    def decision(disposition: StopDisposition, reason: str) -> StoppingDecision:
        return StoppingDecision(
            disposition=disposition,
            reason=reason,
            policy_digest=policy.digest,
            history_digest=history_digest,
            steps_remaining=steps_remaining,
            tokens_remaining=tokens_remaining,
            cost_remaining=round(cost_remaining, 8),
            time_remaining_s=round(time_remaining, 8),
        )

    if latest.explicit_stop:
        return decision(StopDisposition.ABSTAIN, "explicit-stop-requested")

    if latest.elapsed_s >= policy.max_wall_time_s:
        return decision(StopDisposition.DEADLINE, "wall-time-budget-exhausted")
    if (
        latest.step_index >= policy.max_steps
        or latest.cumulative_tokens >= policy.max_tokens
        or latest.cumulative_cost_units >= policy.max_cost_units
    ):
        return decision(
            StopDisposition.BUDGET_EXHAUSTED,
            "reasoning-budget-exhausted",
        )

    high_risk = resolved_risk in {ReasoningRisk.HIGH, ReasoningRisk.CRITICAL}
    verified_enough = (
        not high_risk
        or not policy.require_verification_for_high_risk
        or latest.verification_passed
    )

    if latest.uncertainty > policy.max_uncertainty:
        return decision(
            StopDisposition.ESCALATE,
            "uncertainty-exceeds-policy",
        )

    if (
        latest.confidence >= policy.completion_confidence
        and verified_enough
    ):
        return decision(
            StopDisposition.COMPLETE,
            "completion-confidence-and-verification-satisfied",
        )

    if (
        high_risk
        and policy.require_verification_for_high_risk
        and latest.confidence >= policy.completion_confidence
        and not latest.verification_passed
        and latest.value_of_information < policy.min_value_of_information
    ):
        return decision(
            StopDisposition.ABSTAIN,
            "verification-required-without-remaining-information-value",
        )

    if latest.value_of_information < policy.min_value_of_information:
        return decision(
            StopDisposition.VALUE_EXHAUSTED,
            "value-of-information-below-floor",
        )

    if len(rows) >= policy.max_stall_steps:
        window = rows[-policy.max_stall_steps :]
        if len({row.progress_digest for row in window}) == 1:
            return decision(
                StopDisposition.STALLED,
                "progress-digest-stalled",
            )

    return decision(
        StopDisposition.CONTINUE,
        "bounded-search-has-value-and-budget",
    )


__all__ = [
    "REASONING_POLICY_ACCOUNTABILITY_ID",
    "REASONING_POLICY_SCHEMA_VERSION",
    "REASONING_POLICY_TASK_ID",
    "CognitiveControlDecision",
    "ReasoningBudgetSnapshot",
    "ReasoningPolicy",
    "ReasoningPolicyError",
    "ReasoningPolicyRegistry",
    "ReasoningRisk",
    "ReasoningStep",
    "ReasoningStrategy",
    "StopDisposition",
    "StoppingDecision",
    "StrategyCandidate",
    "StrategyReservation",
    "StrategySelection",
    "evaluate_cognitive_control",
    "evaluate_stopping",
    "reasoning_budget_snapshot",
    "select_strategy",
    "verify_cognitive_control_chain",
]
