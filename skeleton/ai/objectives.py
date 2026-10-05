"""Policy-subordinate objective contracts for VOL-301."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Any, Iterable

from skeleton.contracts.canonical import canonical_json_bytes


class ObjectiveOrigin(str, Enum):
    REQUESTED = "requested"
    INFERRED = "inferred"


class ObjectiveState(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    SATISFIED = "satisfied"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ObjectiveCriterion:
    name: str
    description: str

    def __post_init__(self) -> None:
        if not self.name or self.name.strip() != self.name or not self.name.isascii():
            raise ValueError("criterion name must be non-empty canonical ASCII")
        if not self.description or self.description.strip() != self.description:
            raise ValueError("criterion description must be explicit")


@dataclass(frozen=True)
class Objective:
    statement: str
    origin: ObjectiveOrigin
    criteria: tuple[ObjectiveCriterion, ...]
    parent_id: str | None = None
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.statement or self.statement.strip() != self.statement:
            raise ValueError("objective statement must be explicit")
        if not self.criteria:
            raise ValueError("objective requires success criteria")
        names = [criterion.name for criterion in self.criteria]
        if len(names) != len(set(names)):
            raise ValueError("criterion names must be unique")
        if self.origin is ObjectiveOrigin.REQUESTED and self.parent_id is not None:
            raise ValueError("requested objective cannot masquerade as an inferred subgoal")
        if self.origin is ObjectiveOrigin.INFERRED and not self.parent_id:
            raise ValueError("inferred subgoal requires parent objective identity")
        if any(not c or c.strip() != c for c in self.constraints):
            raise ValueError("constraints must be explicit canonical strings")
        if len(set(self.constraints)) != len(self.constraints):
            raise ValueError("constraints must be unique")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "origin": self.origin.value,
            "criteria": [{"name": c.name, "description": c.description} for c in self.criteria],
            "parent_id": self.parent_id,
            "constraints": list(self.constraints),
        }

    @property
    def identity(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.canonical_payload())).hexdigest()

    def infer(self, statement: str, criteria: Iterable[ObjectiveCriterion], constraints: Iterable[str] = ()) -> "Objective":
        return Objective(statement, ObjectiveOrigin.INFERRED, tuple(criteria), self.identity, tuple(constraints))


@dataclass(frozen=True)
class ObjectiveRecord:
    objective: Objective
    state: ObjectiveState = ObjectiveState.PROPOSED
    satisfied_criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        known = {c.name for c in self.objective.criteria}
        if any(name not in known for name in self.satisfied_criteria):
            raise ValueError("cannot satisfy an undeclared criterion")
        if len(set(self.satisfied_criteria)) != len(self.satisfied_criteria):
            raise ValueError("satisfied criteria must be unique")
        if self.state is ObjectiveState.SATISFIED and set(self.satisfied_criteria) != known:
            raise ValueError("satisfied objective requires every declared criterion")

    def activate(self, *, policy_allowed: bool, authority_allowed: bool) -> "ObjectiveRecord":
        if self.state is not ObjectiveState.PROPOSED:
            raise ValueError("only proposed objectives can activate")
        if not policy_allowed or not authority_allowed:
            return ObjectiveRecord(self.objective, ObjectiveState.BLOCKED, self.satisfied_criteria)
        return ObjectiveRecord(self.objective, ObjectiveState.ACTIVE, self.satisfied_criteria)

    def mark_satisfied(self, criterion_name: str) -> "ObjectiveRecord":
        if self.state is not ObjectiveState.ACTIVE:
            raise ValueError("criteria can be satisfied only for active objectives")
        known = {c.name for c in self.objective.criteria}
        if criterion_name not in known:
            raise ValueError("unknown objective criterion")
        completed = tuple(sorted(set(self.satisfied_criteria) | {criterion_name}))
        state = ObjectiveState.SATISFIED if set(completed) == known else ObjectiveState.ACTIVE
        return ObjectiveRecord(self.objective, state, completed)
