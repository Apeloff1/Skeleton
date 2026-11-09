"""Deterministic latency-budget evidence for AI operations.

This module evaluates declared latency ceilings and stage budgets. Retries are
recorded as evidence but cannot erase or downgrade an observed latency breach.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping


class LatencyBudgetError(ValueError):
    """A latency budget, observation, or assessment invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise LatencyBudgetError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise LatencyBudgetError(f"{name} exceeds maximum length")
    return value


def _positive_ms(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LatencyBudgetError(f"{name} must be finite and positive")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise LatencyBudgetError(f"{name} must be finite and positive")
    return result


def _nonnegative_ms(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LatencyBudgetError(f"{name} must be finite and non-negative")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise LatencyBudgetError(f"{name} must be finite and non-negative")
    return result


def _nonnegative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LatencyBudgetError(f"{name} must be a non-negative integer")
    return value


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LatencyBudgetError("latency evidence must be canonical JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LatencyStage:
    """One named stage allocation within an end-to-end latency budget."""

    stage_id: str
    budget_ms: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_id", _token("stage_id", self.stage_id))
        object.__setattr__(
            self,
            "budget_ms",
            _positive_ms("budget_ms", self.budget_ms),
        )

    @property
    def digest(self) -> str:
        return _digest({"stage_id": self.stage_id, "budget_ms": self.budget_ms})


@dataclass(frozen=True, slots=True)
class LatencyBudget:
    """Percentile and stage ceilings for one operation/environment pair."""

    budget_id: str
    operation_class: str
    environment_id: str
    p95_ms: float
    p99_ms: float
    stages: tuple[LatencyStage, ...]

    def __post_init__(self) -> None:
        for name in ("budget_id", "operation_class", "environment_id"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(self, "p95_ms", _positive_ms("p95_ms", self.p95_ms))
        object.__setattr__(self, "p99_ms", _positive_ms("p99_ms", self.p99_ms))
        if self.p99_ms < self.p95_ms:
            raise LatencyBudgetError("p99 budget cannot be below p95 budget")
        if not isinstance(self.stages, tuple) or not self.stages:
            raise LatencyBudgetError("stages must be a non-empty immutable tuple")
        if any(not isinstance(stage, LatencyStage) for stage in self.stages):
            raise LatencyBudgetError("stages must contain LatencyStage values")
        names = [stage.stage_id for stage in self.stages]
        if len(names) != len(set(names)):
            raise LatencyBudgetError("latency stage IDs must be unique")
        ordered = tuple(sorted(self.stages, key=lambda stage: stage.stage_id))
        if sum(stage.budget_ms for stage in ordered) > self.p99_ms + 1e-12:
            raise LatencyBudgetError(
                "stage budgets cannot oversubscribe p99 end-to-end budget"
            )
        object.__setattr__(self, "stages", ordered)

    @property
    def stage_budgets(self) -> Mapping[str, float]:
        return MappingProxyType(
            {stage.stage_id: stage.budget_ms for stage in self.stages}
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "budget_id": self.budget_id,
                "operation_class": self.operation_class,
                "environment_id": self.environment_id,
                "p95_ms": self.p95_ms,
                "p99_ms": self.p99_ms,
                "stages": [
                    {"stage_id": stage.stage_id, "budget_ms": stage.budget_ms}
                    for stage in self.stages
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class LatencyObservation:
    """Observed tail latency and stage costs with retry count preserved."""

    observation_id: str
    operation_class: str
    environment_id: str
    p95_ms: float
    p99_ms: float
    stage_ms: Mapping[str, float]
    retry_count: int = 0

    def __post_init__(self) -> None:
        for name in ("observation_id", "operation_class", "environment_id"):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        object.__setattr__(self, "p95_ms", _nonnegative_ms("p95_ms", self.p95_ms))
        object.__setattr__(self, "p99_ms", _nonnegative_ms("p99_ms", self.p99_ms))
        if self.p99_ms < self.p95_ms:
            raise LatencyBudgetError("observed p99 cannot be below observed p95")
        if not isinstance(self.stage_ms, Mapping):
            raise LatencyBudgetError("stage_ms must be a mapping")
        canonical: dict[str, float] = {}
        for stage_id, value in self.stage_ms.items():
            clean = _token("stage_id", stage_id)
            if clean in canonical:
                raise LatencyBudgetError("stage_ms IDs must be unique")
            canonical[clean] = _nonnegative_ms(
                f"stage_ms.{clean}",
                value,
            )
        object.__setattr__(
            self,
            "stage_ms",
            MappingProxyType(dict(sorted(canonical.items()))),
        )
        object.__setattr__(
            self,
            "retry_count",
            _nonnegative_int("retry_count", self.retry_count),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "observation_id": self.observation_id,
                "operation_class": self.operation_class,
                "environment_id": self.environment_id,
                "p95_ms": self.p95_ms,
                "p99_ms": self.p99_ms,
                "stage_ms": dict(self.stage_ms),
                "retry_count": self.retry_count,
            }
        )


@dataclass(frozen=True, slots=True)
class LatencyAssessment:
    """Evidence-only budget result; retries never suppress violations."""

    budget_digest: str
    observation_digest: str
    exhausted: bool
    reasons: tuple[str, ...]
    retry_count: int
    retry_override: bool = False

    def __post_init__(self) -> None:
        for name in ("budget_digest", "observation_digest"):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise LatencyBudgetError(f"{name} must be lowercase sha256")
        if not isinstance(self.exhausted, bool):
            raise LatencyBudgetError("exhausted must be boolean")
        reasons = tuple(sorted(set(self.reasons)))
        if any(not isinstance(reason, str) or not reason for reason in reasons):
            raise LatencyBudgetError("reasons must contain non-empty strings")
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(
            self,
            "retry_count",
            _nonnegative_int("retry_count", self.retry_count),
        )
        if self.exhausted != bool(reasons):
            raise LatencyBudgetError("exhausted state must match violation reasons")
        if self.retry_override is not False:
            raise LatencyBudgetError("retries cannot override latency violations")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "budget_digest": self.budget_digest,
                "observation_digest": self.observation_digest,
                "exhausted": self.exhausted,
                "reasons": list(self.reasons),
                "retry_count": self.retry_count,
                "retry_override": False,
            }
        )


def assess_latency(
    *,
    budget: LatencyBudget,
    observation: LatencyObservation,
) -> LatencyAssessment:
    if not isinstance(budget, LatencyBudget):
        raise TypeError("budget must be LatencyBudget")
    if not isinstance(observation, LatencyObservation):
        raise TypeError("observation must be LatencyObservation")
    if (
        budget.operation_class != observation.operation_class
        or budget.environment_id != observation.environment_id
    ):
        raise LatencyBudgetError(
            "latency observation must match budget operation/environment identity"
        )

    reasons: list[str] = []
    if observation.p95_ms > budget.p95_ms:
        reasons.append("p95-budget-exceeded")
    if observation.p99_ms > budget.p99_ms:
        reasons.append("p99-budget-exceeded")

    expected_stages = set(budget.stage_budgets)
    observed_stages = set(observation.stage_ms)
    if observed_stages != expected_stages:
        missing = sorted(expected_stages - observed_stages)
        extra = sorted(observed_stages - expected_stages)
        if missing:
            reasons.append("missing-stages:" + ",".join(missing))
        if extra:
            reasons.append("unknown-stages:" + ",".join(extra))
    for stage_id in sorted(expected_stages & observed_stages):
        if observation.stage_ms[stage_id] > budget.stage_budgets[stage_id]:
            reasons.append(f"stage-budget-exceeded:{stage_id}")

    normalized = tuple(sorted(set(reasons)))
    return LatencyAssessment(
        budget_digest=budget.digest,
        observation_digest=observation.digest,
        exhausted=bool(normalized),
        reasons=normalized,
        retry_count=observation.retry_count,
    )


__all__ = [
    "LatencyAssessment",
    "LatencyBudget",
    "LatencyBudgetError",
    "LatencyObservation",
    "LatencyStage",
    "assess_latency",
]
