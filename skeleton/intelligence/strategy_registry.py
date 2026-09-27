"""Versioned, bounded reasoning/search strategy registry for P1.

The registry chooses an eligible reasoning strategy from explicit capabilities
and hard budgets. It does not execute models, tools, retrieval, or plans.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from skeleton.frontier.contracts import stable_content_digest


REASONING_STRATEGY_SCHEMA_VERSION = 1
REASONING_STRATEGY_TASK_ID = "P1-INTEL-03"
REASONING_STRATEGY_ACCOUNTABILITY_ID = "ACC-P1-INTEL-03"


class ReasoningStrategyError(ValueError):
    """Reasoning strategy policy is malformed or cannot satisfy a request."""


def _text(value: object, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise ReasoningStrategyError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise ReasoningStrategyError(f"{field} must be normalized")
    if len(value) > max_length:
        raise ReasoningStrategyError(f"{field} exceeds maximum length")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReasoningStrategyError(
            f"{field} must be a non-negative integer"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise ReasoningStrategyError(f"{field} must be positive")
    return value


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReasoningStrategyError(
            f"{field} must be finite and non-negative"
        )
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ReasoningStrategyError(
            f"{field} must be finite and non-negative"
        )
    return number


def _unit(value: object, field: str) -> float:
    number = _finite_nonnegative(value, field)
    if number > 1.0:
        raise ReasoningStrategyError(f"{field} must be within [0, 1]")
    return number


def _capabilities(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ReasoningStrategyError(f"{field} must be an iterable")
    rows: list[str] = []
    for value in values:
        token = _text(value, field, max_length=128)
        if token not in rows:
            rows.append(token)
    if not rows:
        raise ReasoningStrategyError(f"{field} must not be empty")
    return tuple(sorted(rows))


@dataclass(frozen=True, slots=True)
class ReasoningBudget:
    iterations: int
    candidates: int
    retrieval_rounds: int
    tool_calls: int
    cost: float
    wall_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "iterations",
            _positive_int(self.iterations, "iterations"),
        )
        object.__setattr__(
            self,
            "candidates",
            _positive_int(self.candidates, "candidates"),
        )
        object.__setattr__(
            self,
            "retrieval_rounds",
            _nonnegative_int(self.retrieval_rounds, "retrieval_rounds"),
        )
        object.__setattr__(
            self,
            "tool_calls",
            _nonnegative_int(self.tool_calls, "tool_calls"),
        )
        object.__setattr__(self, "cost", _finite_nonnegative(self.cost, "cost"))
        if self.cost <= 0.0:
            raise ReasoningStrategyError("cost must be positive")
        object.__setattr__(
            self,
            "wall_seconds",
            _finite_nonnegative(self.wall_seconds, "wall_seconds"),
        )
        if self.wall_seconds <= 0.0:
            raise ReasoningStrategyError("wall_seconds must be positive")

    def as_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "candidates": self.candidates,
            "retrieval_rounds": self.retrieval_rounds,
            "tool_calls": self.tool_calls,
            "cost": self.cost,
            "wall_seconds": self.wall_seconds,
        }

    def constrain(self, other: "ReasoningBudget") -> "ReasoningBudget":
        if not isinstance(other, ReasoningBudget):
            raise TypeError("other must be ReasoningBudget")
        return ReasoningBudget(
            iterations=min(self.iterations, other.iterations),
            candidates=min(self.candidates, other.candidates),
            retrieval_rounds=min(
                self.retrieval_rounds,
                other.retrieval_rounds,
            ),
            tool_calls=min(self.tool_calls, other.tool_calls),
            cost=min(self.cost, other.cost),
            wall_seconds=min(self.wall_seconds, other.wall_seconds),
        )


@dataclass(frozen=True, slots=True)
class StopPolicy:
    min_evidence_gain: float
    min_value_of_information: float
    abstain_uncertainty: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "min_evidence_gain",
            _unit(self.min_evidence_gain, "min_evidence_gain"),
        )
        object.__setattr__(
            self,
            "min_value_of_information",
            _unit(
                self.min_value_of_information,
                "min_value_of_information",
            ),
        )
        object.__setattr__(
            self,
            "abstain_uncertainty",
            _unit(self.abstain_uncertainty, "abstain_uncertainty"),
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "min_evidence_gain": self.min_evidence_gain,
            "min_value_of_information": self.min_value_of_information,
            "abstain_uncertainty": self.abstain_uncertainty,
        }


@dataclass(frozen=True, slots=True)
class ReasoningStrategy:
    strategy_id: str
    priority: int
    capabilities: tuple[str, ...]
    description: str
    limits: ReasoningBudget
    stop_policy: StopPolicy

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strategy_id",
            _text(self.strategy_id, "strategy_id", max_length=128),
        )
        object.__setattr__(
            self,
            "priority",
            _nonnegative_int(self.priority, "priority"),
        )
        object.__setattr__(
            self,
            "capabilities",
            _capabilities(self.capabilities, "capabilities"),
        )
        object.__setattr__(
            self,
            "description",
            _text(self.description, "description", max_length=1024),
        )
        if not isinstance(self.limits, ReasoningBudget):
            raise ReasoningStrategyError("limits must be ReasoningBudget")
        if not isinstance(self.stop_policy, StopPolicy):
            raise ReasoningStrategyError("stop_policy must be StopPolicy")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.strategy_id,
            "priority": self.priority,
            "capabilities": list(self.capabilities),
            "description": self.description,
            "limits": self.limits.as_dict(),
            "stop": self.stop_policy.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class ReasoningStrategyRegistry:
    registry_id: str
    registry_version: str
    strategies: tuple[ReasoningStrategy, ...]
    task_id: str = REASONING_STRATEGY_TASK_ID
    accountability_ref: str = REASONING_STRATEGY_ACCOUNTABILITY_ID
    schema_version: int = REASONING_STRATEGY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != REASONING_STRATEGY_SCHEMA_VERSION:
            raise ReasoningStrategyError("unsupported registry schema")
        if self.task_id != REASONING_STRATEGY_TASK_ID:
            raise ReasoningStrategyError("task_id drift")
        if self.accountability_ref != REASONING_STRATEGY_ACCOUNTABILITY_ID:
            raise ReasoningStrategyError("accountability_ref drift")
        object.__setattr__(
            self,
            "registry_id",
            _text(self.registry_id, "registry_id", max_length=256),
        )
        object.__setattr__(
            self,
            "registry_version",
            _text(self.registry_version, "registry_version", max_length=64),
        )
        if not self.strategies:
            raise ReasoningStrategyError("registry requires strategies")
        ids = tuple(item.strategy_id for item in self.strategies)
        if len(ids) != len(set(ids)):
            raise ReasoningStrategyError("strategy ids must be unique")

    @property
    def digest(self) -> str:
        return stable_content_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "task_id": self.task_id,
            "accountability_ref": self.accountability_ref,
            "strategies": [
                item.as_dict()
                for item in sorted(
                    self.strategies,
                    key=lambda row: (row.priority, row.strategy_id),
                )
            ],
        }

    def by_id(self, strategy_id: str) -> ReasoningStrategy:
        target = _text(strategy_id, "strategy_id", max_length=128)
        for strategy in self.strategies:
            if strategy.strategy_id == target:
                return strategy
        raise KeyError(target)


@dataclass(frozen=True, slots=True)
class ReasoningRequestProfile:
    request_id: str
    required_capabilities: tuple[str, ...]
    budget: ReasoningBudget
    allowed_strategy_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _text(self.request_id, "request_id", max_length=256),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _capabilities(
                self.required_capabilities,
                "required_capabilities",
            ),
        )
        if not isinstance(self.budget, ReasoningBudget):
            raise ReasoningStrategyError("budget must be ReasoningBudget")
        if self.allowed_strategy_ids:
            object.__setattr__(
                self,
                "allowed_strategy_ids",
                _capabilities(
                    self.allowed_strategy_ids,
                    "allowed_strategy_ids",
                ),
            )


@dataclass(frozen=True, slots=True)
class StrategySelection:
    request_id: str
    registry_digest: str
    strategy_id: str
    effective_budget: ReasoningBudget
    required_capabilities: tuple[str, ...]

    @property
    def digest(self) -> str:
        return stable_content_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "registry_digest": self.registry_digest,
            "strategy_id": self.strategy_id,
            "effective_budget": self.effective_budget.as_dict(),
            "required_capabilities": list(self.required_capabilities),
        }


def select_reasoning_strategy(
    registry: ReasoningStrategyRegistry,
    request: ReasoningRequestProfile,
) -> StrategySelection:
    if not isinstance(registry, ReasoningStrategyRegistry):
        raise TypeError("registry must be ReasoningStrategyRegistry")
    if not isinstance(request, ReasoningRequestProfile):
        raise TypeError("request must be ReasoningRequestProfile")

    required = set(request.required_capabilities)
    allowed = set(request.allowed_strategy_ids)
    candidates = []
    for strategy in registry.strategies:
        if allowed and strategy.strategy_id not in allowed:
            continue
        if not required.issubset(set(strategy.capabilities)):
            continue
        effective = strategy.limits.constrain(request.budget)
        candidates.append((strategy.priority, strategy.strategy_id, strategy, effective))

    if not candidates:
        raise ReasoningStrategyError(
            "no eligible reasoning strategy for required capabilities"
        )
    _, _, strategy, effective = min(candidates, key=lambda row: (row[0], row[1]))
    return StrategySelection(
        request_id=request.request_id,
        registry_digest=registry.digest,
        strategy_id=strategy.strategy_id,
        effective_budget=effective,
        required_capabilities=request.required_capabilities,
    )


def _strategy_from_payload(row: Mapping[str, Any]) -> ReasoningStrategy:
    limits = row.get("limits")
    stop = row.get("stop")
    if not isinstance(limits, Mapping) or not isinstance(stop, Mapping):
        raise ReasoningStrategyError("strategy limits/stop must be objects")
    raw_capabilities = row.get("capabilities")
    if not isinstance(raw_capabilities, list):
        raise ReasoningStrategyError("strategy capabilities must be a list")
    return ReasoningStrategy(
        strategy_id=row.get("id"),
        priority=row.get("priority"),
        capabilities=tuple(raw_capabilities),
        description=row.get("description"),
        limits=ReasoningBudget(
            iterations=limits.get("iterations"),
            candidates=limits.get("candidates"),
            retrieval_rounds=limits.get("retrieval_rounds"),
            tool_calls=limits.get("tool_calls"),
            cost=limits.get("cost"),
            wall_seconds=limits.get("wall_seconds"),
        ),
        stop_policy=StopPolicy(
            min_evidence_gain=stop.get("min_evidence_gain"),
            min_value_of_information=stop.get("min_value_of_information"),
            abstain_uncertainty=stop.get("abstain_uncertainty"),
        ),
    )


def registry_from_payload(
    payload: Mapping[str, Any],
) -> ReasoningStrategyRegistry:
    if not isinstance(payload, Mapping):
        raise TypeError("registry payload must be a mapping")
    rows = payload.get("strategies")
    if not isinstance(rows, list):
        raise ReasoningStrategyError("strategies must be a list")
    return ReasoningStrategyRegistry(
        registry_id=payload.get("registry_id"),
        registry_version=payload.get("registry_version"),
        strategies=tuple(_strategy_from_payload(row) for row in rows),
        task_id=payload.get("task_id"),
        accountability_ref=payload.get("accountability_ref"),
        schema_version=payload.get("schema_version"),
    )


def load_reasoning_strategy_registry(
    path: str | Path,
) -> ReasoningStrategyRegistry:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReasoningStrategyError(
            f"cannot load reasoning strategy registry: {target}"
        ) from exc
    return registry_from_payload(payload)


__all__ = [
    "REASONING_STRATEGY_ACCOUNTABILITY_ID",
    "REASONING_STRATEGY_SCHEMA_VERSION",
    "REASONING_STRATEGY_TASK_ID",
    "ReasoningBudget",
    "ReasoningRequestProfile",
    "ReasoningStrategy",
    "ReasoningStrategyError",
    "ReasoningStrategyRegistry",
    "StopPolicy",
    "StrategySelection",
    "load_reasoning_strategy_registry",
    "registry_from_payload",
    "select_reasoning_strategy",
]
