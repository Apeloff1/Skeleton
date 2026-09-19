from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .models import MAX_ITEMS, Plan, RiskTier, Step


class ConstraintKind(str, Enum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"
    BUDGET = "budget"
    DEPENDENCY = "dependency"
    EVIDENCE = "evidence"
    AUTHORITY = "authority"
    SAFETY = "safety"


@dataclass(frozen=True, slots=True)
class Constraint:
    name: str
    kind: ConstraintKind
    limit: int | None = None
    value: str | None = None

    def __post_init__(self) -> None:
        if not self.name or len(self.name) > 256 or "\x00" in self.name:
            raise ValueError("invalid constraint name")
        if self.limit is not None and not 0 <= self.limit <= 1_000_000:
            raise ValueError("constraint limit out of bounds")
        if self.value is not None and (not self.value or len(self.value) > 4096):
            raise ValueError("invalid constraint value")


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    constraint: str
    subject: str
    reason: str


@dataclass(frozen=True, slots=True)
class ConstraintReport:
    checked: int
    violations: tuple[ConstraintViolation, ...]

    @property
    def valid(self) -> bool:
        return not self.violations


def check_required_steps(plan: Plan, constraints: Iterable[Constraint]) -> list[ConstraintViolation]:
    names = {step.name for step in plan.steps}
    out: list[ConstraintViolation] = []
    for c in constraints:
        if c.kind is ConstraintKind.REQUIRED and c.value and c.value not in names:
            out.append(ConstraintViolation(c.name, c.value, "required step is missing"))
    return out


def check_forbidden_actions(plan: Plan, constraints: Iterable[Constraint]) -> list[ConstraintViolation]:
    out: list[ConstraintViolation] = []
    for step in plan.steps:
        for c in constraints:
            if c.kind is ConstraintKind.FORBIDDEN and c.value and c.value.casefold() in step.action.casefold():
                out.append(ConstraintViolation(c.name, step.name, "forbidden action pattern"))
    return out


def check_budget(plan: Plan, constraints: Iterable[Constraint]) -> list[ConstraintViolation]:
    out: list[ConstraintViolation] = []
    count = len(plan.steps)
    for c in constraints:
        if c.kind is ConstraintKind.BUDGET and c.limit is not None and count > c.limit:
            out.append(ConstraintViolation(c.name, "plan", f"step count {count} exceeds {c.limit}"))
    return out


def check_evidence(plan: Plan, constraints: Iterable[Constraint]) -> list[ConstraintViolation]:
    out: list[ConstraintViolation] = []
    require = any(c.kind is ConstraintKind.EVIDENCE for c in constraints)
    if require:
        for step in plan.steps:
            if not step.evidence_required:
                out.append(ConstraintViolation("evidence", step.name, "evidence is required"))
    return out


def check_risk(plan: Plan, maximum: RiskTier = RiskTier.HIGH) -> list[ConstraintViolation]:
    order = {RiskTier.LOW: 0, RiskTier.MEDIUM: 1, RiskTier.HIGH: 2, RiskTier.CRITICAL: 3}
    return [ConstraintViolation("risk", step.name, "risk exceeds plan ceiling") for step in plan.steps if order[step.risk] > order[maximum]]


def validate_constraints(plan: Plan, constraints: tuple[Constraint, ...]) -> ConstraintReport:
    if len(constraints) > MAX_ITEMS:
        raise ValueError("too many constraints")
    violations = []
    violations.extend(check_required_steps(plan, constraints))
    violations.extend(check_forbidden_actions(plan, constraints))
    violations.extend(check_budget(plan, constraints))
    violations.extend(check_evidence(plan, constraints))
    return ConstraintReport(len(constraints), tuple(violations))


def require_valid(plan: Plan, constraints: tuple[Constraint, ...]) -> None:
    report = validate_constraints(plan, constraints)
    if not report.valid:
        raise ValueError("; ".join(v.reason for v in report.violations))


def normalize_constraints(items: Iterable[Constraint]) -> tuple[Constraint, ...]:
    result = tuple(items)
    names = [item.name for item in result]
    if len(names) != len(set(names)):
        raise ValueError("duplicate constraint name")
    return tuple(sorted(result, key=lambda c: c.name))
