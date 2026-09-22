from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from typing import Any, Mapping

MAX_TEXT = 4096
MAX_ITEMS = 256
MAX_METADATA = 64


def _clean_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT or "\x00" in value:
        raise ValueError(f"invalid {field_name}")
    return value


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


class PlanState(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    BLOCKED = "blocked"
    APPROVED = "approved"
    EXECUTED = "executed"
    REJECTED = "rejected"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class Goal:
    name: str
    description: str
    priority: int = 0
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _clean_text(self.name, field_name="goal name")
        _clean_text(self.description, field_name="goal description")
        if not 0 <= self.priority <= 100:
            raise ValueError("goal priority out of bounds")
        if len(self.constraints) > MAX_ITEMS:
            raise ValueError("too many constraints")
        for item in self.constraints:
            _clean_text(item, field_name="constraint")

    @property
    def id(self) -> str:
        return fingerprint({"name": self.name, "description": self.description, "priority": self.priority, "constraints": self.constraints})


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    action: str
    depends_on: tuple[str, ...] = ()
    evidence_required: bool = True
    risk: RiskTier = RiskTier.LOW
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _clean_text(self.name, field_name="step name")
        _clean_text(self.action, field_name="step action")
        if len(self.depends_on) > MAX_ITEMS:
            raise ValueError("too many dependencies")
        if len(self.metadata) > MAX_METADATA:
            raise ValueError("too much metadata")
        seen: set[str] = set()
        for dep in self.depends_on:
            _clean_text(dep, field_name="dependency")
            if dep in seen:
                raise ValueError("duplicate dependency")
            seen.add(dep)
        for key, value in self.metadata:
            _clean_text(key, field_name="metadata key")
            _clean_text(value, field_name="metadata value")

    @property
    def id(self) -> str:
        return fingerprint({"name": self.name, "action": self.action, "depends_on": self.depends_on, "evidence_required": self.evidence_required, "risk": self.risk.value, "metadata": self.metadata})


@dataclass(frozen=True, slots=True)
class Plan:
    goal: Goal
    steps: tuple[Step, ...]
    state: PlanState = PlanState.DRAFT
    assumptions: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.steps or len(self.steps) > MAX_ITEMS:
            raise ValueError("invalid step count")
        if len(self.assumptions) > MAX_ITEMS or len(self.labels) > MAX_ITEMS:
            raise ValueError("too many plan annotations")
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("duplicate step name")
        known = set(names)
        for step in self.steps:
            if step.name in step.depends_on:
                raise ValueError("self dependency")
            if not set(step.depends_on) <= known:
                raise ValueError("unknown dependency")
        _assert_acyclic(self.steps)
        for item in (*self.assumptions, *self.labels):
            _clean_text(item, field_name="plan annotation")

    @property
    def id(self) -> str:
        return fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"goal": {"name": self.goal.name, "description": self.goal.description, "priority": self.goal.priority, "constraints": self.goal.constraints}, "steps": [{"name": s.name, "action": s.action, "depends_on": s.depends_on, "evidence_required": s.evidence_required, "risk": s.risk.value, "metadata": s.metadata} for s in self.steps], "state": self.state.value, "assumptions": self.assumptions, "labels": self.labels}


def _assert_acyclic(steps: tuple[Step, ...]) -> None:
    graph = {s.name: set(s.depends_on) for s in steps}
    visiting: set[str] = set()
    done: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("dependency cycle")
        if node in done:
            return
        visiting.add(node)
        for parent in graph[node]:
            visit(parent)
        visiting.remove(node)
        done.add(node)
    for name in graph:
        visit(name)


def topological_order(plan: Plan) -> tuple[str, ...]:
    remaining = {s.name: set(s.depends_on) for s in plan.steps}
    result: list[str] = []
    while remaining:
        ready = sorted(name for name, deps in remaining.items() if not deps)
        if not ready:
            raise ValueError("dependency cycle")
        result.extend(ready)
        for name in ready:
            remaining.pop(name)
        for deps in remaining.values():
            deps.difference_update(ready)
    return tuple(result)


def with_state(plan: Plan, state: PlanState) -> Plan:
    allowed = {PlanState.DRAFT: {PlanState.READY, PlanState.REJECTED}, PlanState.READY: {PlanState.APPROVED, PlanState.BLOCKED, PlanState.REJECTED}, PlanState.BLOCKED: {PlanState.READY, PlanState.REJECTED}, PlanState.APPROVED: {PlanState.EXECUTED, PlanState.REJECTED}, PlanState.EXECUTED: set(), PlanState.REJECTED: set()}
    if state not in allowed[plan.state]:
        raise ValueError(f"invalid plan transition {plan.state.value}->{state.value}")
    return Plan(goal=plan.goal, steps=plan.steps, state=state, assumptions=plan.assumptions, labels=plan.labels)


def merge_metadata(*sources: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    merged: dict[str, str] = {}
    for source in sources:
        for key, value in source.items():
            _clean_text(key, field_name="metadata key")
            _clean_text(value, field_name="metadata value")
            merged[key] = value
    if len(merged) > MAX_METADATA:
        raise ValueError("metadata limit exceeded")
    return tuple(sorted(merged.items()))
