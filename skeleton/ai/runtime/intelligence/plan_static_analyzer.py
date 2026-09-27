"""Deterministic pre-execution plan static analysis for P1-INTEL-05.

This module does not execute plans. It proves that a candidate plan is a
bounded DAG whose capabilities, budgets, pre/postconditions, terminal behavior,
retry semantics, and recovery declarations fit an exact INTEL-03 reasoning
policy before runtime execution is allowed to consume the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.intelligence.strategy_registry import ReasoningPolicy


PLAN_ANALYSIS_SCHEMA_VERSION = 1
PLAN_ANALYSIS_TASK_ID = "P1-INTEL-05"
PLAN_ANALYSIS_ACCOUNTABILITY_ID = "ACC-P1-INTEL-05"
_MAX_STEPS = 1024
_MAX_RETRIES = 32
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class PlanStaticAnalysisError(ValueError):
    """Plan static-analysis input is malformed."""


class FailurePolicy(str, Enum):
    ABORT = "abort"
    RETRY = "retry"
    COMPENSATE = "compensate"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise PlanStaticAnalysisError(f"{field} must be a canonical token")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
        raise PlanStaticAnalysisError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PlanStaticAnalysisError(f"{field} must be a positive integer")
    return value


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PlanStaticAnalysisError(f"{field} must be a non-negative integer")
    return value


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanStaticAnalysisError(f"{field} must be positive finite numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise PlanStaticAnalysisError(f"{field} must be positive finite numeric")
    return number


def _nonnegative_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanStaticAnalysisError(f"{field} must be non-negative finite numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise PlanStaticAnalysisError(f"{field} must be non-negative finite numeric")
    return number


def _tokens(
    values: Iterable[str],
    field: str,
    *,
    allow_empty: bool = True,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PlanStaticAnalysisError(f"{field} must be an iterable")
    result = tuple(sorted({_token(value, field) for value in values}))
    if not result and not allow_empty:
        raise PlanStaticAnalysisError(f"{field} must be non-empty")
    if len(result) > _MAX_STEPS:
        raise PlanStaticAnalysisError(f"{field} exceeds item limit")
    return result


def _statements(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise PlanStaticAnalysisError(f"{field} must be an iterable")
    result: list[str] = []
    for value in values:
        if (
            not isinstance(value, str)
            or not value.strip()
            or value != value.strip()
            or len(value) > 512
        ):
            raise PlanStaticAnalysisError(
                f"{field} entries must be normalized non-empty text"
            )
        if value not in result:
            result.append(value)
    if len(result) > 256:
        raise PlanStaticAnalysisError(f"{field} exceeds item limit")
    return tuple(result)


def _canonical_digest(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlanStaticAnalysisError("plan payload must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class PlanBudget:
    max_steps: int
    max_tokens: int
    max_cost_units: float
    max_wall_time_s: float
    max_retries_per_step: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_steps", _positive_int(self.max_steps, "max_steps"))
        object.__setattr__(self, "max_tokens", _positive_int(self.max_tokens, "max_tokens"))
        object.__setattr__(
            self,
            "max_cost_units",
            _positive_number(self.max_cost_units, "max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_wall_time_s",
            _positive_number(self.max_wall_time_s, "max_wall_time_s"),
        )
        retries = _nonnegative_int(self.max_retries_per_step, "max_retries_per_step")
        if retries > _MAX_RETRIES:
            raise PlanStaticAnalysisError("max_retries_per_step exceeds hard limit")
        object.__setattr__(self, "max_retries_per_step", retries)

    def payload(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
            "max_retries_per_step": self.max_retries_per_step,
        }


@dataclass(frozen=True, slots=True)
class PlanStepSpec:
    step_id: str
    depends_on: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    preconditions: tuple[str, ...]
    postconditions: tuple[str, ...]
    max_tokens: int
    max_cost_units: float
    max_wall_time_s: float
    failure_policy: FailurePolicy = FailurePolicy.ABORT
    max_retries: int = 0
    side_effecting: bool = False
    idempotent: bool = True
    recovery_action: str | None = None
    terminal: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_id", _token(self.step_id, "step_id"))
        object.__setattr__(
            self,
            "depends_on",
            _tokens(self.depends_on, "depends_on"),
        )
        object.__setattr__(
            self,
            "required_capabilities",
            _tokens(self.required_capabilities, "required_capabilities"),
        )
        object.__setattr__(
            self,
            "preconditions",
            _statements(self.preconditions, "preconditions"),
        )
        object.__setattr__(
            self,
            "postconditions",
            _statements(self.postconditions, "postconditions"),
        )
        object.__setattr__(
            self,
            "max_tokens",
            _nonnegative_int(self.max_tokens, "step.max_tokens"),
        )
        object.__setattr__(
            self,
            "max_cost_units",
            _nonnegative_number(self.max_cost_units, "step.max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_wall_time_s",
            _positive_number(self.max_wall_time_s, "step.max_wall_time_s"),
        )
        try:
            object.__setattr__(self, "failure_policy", FailurePolicy(self.failure_policy))
        except ValueError as exc:
            raise PlanStaticAnalysisError("invalid failure_policy") from exc
        retries = _nonnegative_int(self.max_retries, "max_retries")
        if retries > _MAX_RETRIES:
            raise PlanStaticAnalysisError("max_retries exceeds hard limit")
        object.__setattr__(self, "max_retries", retries)
        if not isinstance(self.side_effecting, bool):
            raise PlanStaticAnalysisError("side_effecting must be boolean")
        if not isinstance(self.idempotent, bool):
            raise PlanStaticAnalysisError("idempotent must be boolean")
        if not isinstance(self.terminal, bool):
            raise PlanStaticAnalysisError("terminal must be boolean")
        if self.recovery_action is not None:
            object.__setattr__(
                self,
                "recovery_action",
                _token(self.recovery_action, "recovery_action"),
            )

    def payload(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "depends_on": list(self.depends_on),
            "required_capabilities": list(self.required_capabilities),
            "preconditions": list(self.preconditions),
            "postconditions": list(self.postconditions),
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
            "failure_policy": self.failure_policy.value,
            "max_retries": self.max_retries,
            "side_effecting": self.side_effecting,
            "idempotent": self.idempotent,
            "recovery_action": self.recovery_action,
            "terminal": self.terminal,
        }


@dataclass(frozen=True, slots=True)
class ExecutionPlanSpec:
    plan_id: str
    reasoning_policy_digest: str
    allowed_capabilities: tuple[str, ...]
    budget: PlanBudget
    steps: tuple[PlanStepSpec, ...]
    schema_version: int = PLAN_ANALYSIS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _token(self.plan_id, "plan_id"))
        object.__setattr__(
            self,
            "reasoning_policy_digest",
            _digest(self.reasoning_policy_digest, "reasoning_policy_digest"),
        )
        object.__setattr__(
            self,
            "allowed_capabilities",
            _tokens(
                self.allowed_capabilities,
                "allowed_capabilities",
                allow_empty=False,
            ),
        )
        if not isinstance(self.budget, PlanBudget):
            raise PlanStaticAnalysisError("budget must be PlanBudget")
        if (
            not isinstance(self.steps, tuple)
            or not self.steps
            or len(self.steps) > _MAX_STEPS
            or any(not isinstance(step, PlanStepSpec) for step in self.steps)
        ):
            raise PlanStaticAnalysisError("steps must be a bounded non-empty tuple")
        if self.schema_version != PLAN_ANALYSIS_SCHEMA_VERSION:
            raise PlanStaticAnalysisError("unsupported plan schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "reasoning_policy_digest": self.reasoning_policy_digest,
            "allowed_capabilities": list(self.allowed_capabilities),
            "budget": self.budget.payload(),
            "steps": [
                step.payload()
                for step in sorted(self.steps, key=lambda item: item.step_id)
            ],
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class PlanStaticAnalysisDecision:
    accepted: bool
    plan_digest: str
    reasoning_policy_digest: str
    findings: tuple[str, ...]
    step_count: int
    terminal_count: int
    aggregate_tokens: int
    aggregate_cost_units: float
    critical_path_wall_time_s: float
    task_id: str = PLAN_ANALYSIS_TASK_ID
    accountability_id: str = PLAN_ANALYSIS_ACCOUNTABILITY_ID
    schema_version: int = PLAN_ANALYSIS_SCHEMA_VERSION

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "plan_digest": self.plan_digest,
            "reasoning_policy_digest": self.reasoning_policy_digest,
            "findings": list(self.findings),
            "step_count": self.step_count,
            "terminal_count": self.terminal_count,
            "aggregate_tokens": self.aggregate_tokens,
            "aggregate_cost_units": self.aggregate_cost_units,
            "critical_path_wall_time_s": self.critical_path_wall_time_s,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise PlanStaticAnalysisError(
                "rejected plan analysis cannot become promotion evidence"
            )
        return EvidenceRef(
            source="p1:intel-05:plan-static-analysis",
            digest=self.decision_digest,
            category="plan_static_analysis",
        )


def _critical_path_wall(
    by_id: dict[str, PlanStepSpec],
    dependencies: dict[str, set[str]],
) -> tuple[float, bool]:
    visiting: set[str] = set()
    visited: set[str] = set()
    order: list[str] = []
    cycle = False

    def visit(step_id: str) -> None:
        nonlocal cycle
        if step_id in visiting:
            cycle = True
            return
        if step_id in visited:
            return
        visiting.add(step_id)
        for dep in sorted(dependencies.get(step_id, ())):
            if dep in by_id:
                visit(dep)
        visiting.remove(step_id)
        visited.add(step_id)
        order.append(step_id)

    for step_id in sorted(by_id):
        visit(step_id)
    if cycle:
        return 0.0, True

    longest: dict[str, float] = {}
    for step_id in order:
        dep_time = max(
            (longest[dep] for dep in dependencies[step_id] if dep in longest),
            default=0.0,
        )
        longest[step_id] = dep_time + by_id[step_id].max_wall_time_s
    return max(longest.values(), default=0.0), False


def analyze_plan(
    plan: ExecutionPlanSpec,
    *,
    reasoning_policy: ReasoningPolicy,
) -> PlanStaticAnalysisDecision:
    if not isinstance(plan, ExecutionPlanSpec):
        raise TypeError("plan must be ExecutionPlanSpec")
    if not isinstance(reasoning_policy, ReasoningPolicy):
        raise TypeError("reasoning_policy must be ReasoningPolicy")

    findings: list[str] = []
    if plan.reasoning_policy_digest != reasoning_policy.digest:
        findings.append("policy:digest-mismatch")
    if plan.budget.max_steps > reasoning_policy.max_steps:
        findings.append("budget:steps-exceed-reasoning-policy")
    if plan.budget.max_tokens > reasoning_policy.max_tokens:
        findings.append("budget:tokens-exceed-reasoning-policy")
    if plan.budget.max_cost_units > reasoning_policy.max_cost_units:
        findings.append("budget:cost-exceeds-reasoning-policy")
    if plan.budget.max_wall_time_s > reasoning_policy.max_wall_time_s:
        findings.append("budget:wall-time-exceeds-reasoning-policy")
    if len(plan.steps) > plan.budget.max_steps:
        findings.append("budget:step-count-exceeded")

    by_id: dict[str, PlanStepSpec] = {}
    duplicates: set[str] = set()
    for step in plan.steps:
        if step.step_id in by_id:
            duplicates.add(step.step_id)
        by_id[step.step_id] = step
    for step_id in sorted(duplicates):
        findings.append(f"graph:duplicate-step:{step_id}")

    dependencies = {
        step_id: set(step.depends_on)
        for step_id, step in by_id.items()
    }
    dependents: dict[str, set[str]] = {step_id: set() for step_id in by_id}
    allowed_capabilities = set(plan.allowed_capabilities)

    for step_id, step in sorted(by_id.items()):
        if step_id in dependencies[step_id]:
            findings.append(f"graph:self-dependency:{step_id}")
        for dep in sorted(dependencies[step_id]):
            if dep not in by_id:
                findings.append(f"graph:unknown-dependency:{step_id}:{dep}")
            else:
                dependents[dep].add(step_id)

        missing_capabilities = set(step.required_capabilities) - allowed_capabilities
        for capability in sorted(missing_capabilities):
            findings.append(
                f"authority:capability-widening:{step_id}:{capability}"
            )
        if not step.preconditions:
            findings.append(f"contract:missing-preconditions:{step_id}")
        if not step.postconditions:
            findings.append(f"contract:missing-postconditions:{step_id}")
        if step.max_tokens > plan.budget.max_tokens:
            findings.append(f"budget:step-token-limit:{step_id}")
        if step.max_cost_units > plan.budget.max_cost_units:
            findings.append(f"budget:step-cost-limit:{step_id}")
        if step.max_wall_time_s > plan.budget.max_wall_time_s:
            findings.append(f"budget:step-wall-limit:{step_id}")

        if step.failure_policy is FailurePolicy.RETRY:
            if step.max_retries < 1:
                findings.append(f"recovery:retry-without-attempts:{step_id}")
            if step.max_retries > plan.budget.max_retries_per_step:
                findings.append(f"recovery:retry-budget-exceeded:{step_id}")
            if not step.idempotent:
                findings.append(f"recovery:retry-non-idempotent:{step_id}")
        elif step.max_retries != 0:
            findings.append(f"recovery:retries-without-retry-policy:{step_id}")

        if step.side_effecting:
            if step.failure_policy is not FailurePolicy.COMPENSATE:
                findings.append(f"recovery:side-effect-without-compensation:{step_id}")
            if step.recovery_action is None:
                findings.append(f"recovery:missing-recovery-action:{step_id}")
        elif step.failure_policy is FailurePolicy.COMPENSATE:
            findings.append(f"recovery:compensation-on-read-only-step:{step_id}")
        elif step.recovery_action is not None:
            findings.append(f"recovery:orphan-recovery-action:{step_id}")

    critical_path, cycle = _critical_path_wall(by_id, dependencies)
    if cycle:
        findings.append("graph:cycle")
    if not cycle:
        terminals = {step_id for step_id, step in by_id.items() if step.terminal}
        if not terminals:
            findings.append("graph:no-terminal-step")
        for step_id in sorted(terminals):
            if dependents[step_id]:
                findings.append(f"graph:terminal-has-dependent:{step_id}")
        for step_id, outgoing in sorted(dependents.items()):
            if not outgoing and step_id not in terminals:
                findings.append(f"graph:sink-not-terminal:{step_id}")
        if critical_path > plan.budget.max_wall_time_s:
            findings.append("budget:critical-path-wall-time-exceeded")

    aggregate_tokens = sum(step.max_tokens for step in plan.steps)
    aggregate_cost = round(sum(step.max_cost_units for step in plan.steps), 8)
    if aggregate_tokens > plan.budget.max_tokens:
        findings.append("budget:aggregate-tokens-exceeded")
    if aggregate_cost > plan.budget.max_cost_units:
        findings.append("budget:aggregate-cost-exceeded")

    terminal_count = sum(1 for step in plan.steps if step.terminal)
    normalized = tuple(sorted(set(findings)))
    return PlanStaticAnalysisDecision(
        accepted=not normalized,
        plan_digest=plan.digest,
        reasoning_policy_digest=reasoning_policy.digest,
        findings=normalized,
        step_count=len(plan.steps),
        terminal_count=terminal_count,
        aggregate_tokens=aggregate_tokens,
        aggregate_cost_units=aggregate_cost,
        critical_path_wall_time_s=round(critical_path, 8),
    )


__all__ = [
    "PLAN_ANALYSIS_ACCOUNTABILITY_ID",
    "PLAN_ANALYSIS_SCHEMA_VERSION",
    "PLAN_ANALYSIS_TASK_ID",
    "ExecutionPlanSpec",
    "FailurePolicy",
    "PlanBudget",
    "PlanStaticAnalysisDecision",
    "PlanStaticAnalysisError",
    "PlanStepSpec",
    "analyze_plan",
]
