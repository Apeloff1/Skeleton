"""Fail-closed hard/soft constraint evaluation for VOL-303."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generic, Iterable, TypeVar

T = TypeVar("T")


class ConstraintStrength(str, Enum):
    HARD = "hard"
    SOFT = "soft"


@dataclass(frozen=True)
class Constraint(Generic[T]):
    constraint_id: str
    description: str
    strength: ConstraintStrength
    provenance: str
    predicate: Callable[[T], bool]

    def __post_init__(self) -> None:
        for value, label in (
            (self.constraint_id, "constraint_id"),
            (self.description, "description"),
            (self.provenance, "provenance"),
        ):
            if not isinstance(value, str) or not value or value.strip() != value:
                raise ValueError(f"{label} must be explicit")


@dataclass(frozen=True)
class ConstraintViolation:
    constraint_id: str
    strength: ConstraintStrength
    provenance: str
    description: str


@dataclass(frozen=True)
class ConstraintResult:
    admissible: bool
    hard_violations: tuple[ConstraintViolation, ...]
    soft_violations: tuple[ConstraintViolation, ...]
    evaluation_errors: tuple[str, ...]

    @property
    def utility_eligible(self) -> bool:
        """Utility scoring is legal only after every hard constraint passes."""
        return self.admissible


@dataclass(frozen=True)
class ConstraintSet(Generic[T]):
    constraints: tuple[Constraint[T], ...]

    def __post_init__(self) -> None:
        ids = [item.constraint_id for item in self.constraints]
        if len(ids) != len(set(ids)):
            raise ValueError("constraint IDs must be unique")

    @classmethod
    def of(cls, constraints: Iterable[Constraint[T]]) -> "ConstraintSet[T]":
        return cls(tuple(constraints))

    def evaluate(self, candidate: T) -> ConstraintResult:
        hard: list[ConstraintViolation] = []
        soft: list[ConstraintViolation] = []
        errors: list[str] = []
        for constraint in sorted(self.constraints, key=lambda item: item.constraint_id):
            try:
                passed = constraint.predicate(candidate)
                if not isinstance(passed, bool):
                    raise TypeError("constraint predicate must return bool")
            except Exception as exc:
                # A broken hard check is itself a hard denial. A broken soft
                # check remains explicit evidence and cannot silently pass.
                errors.append(f"{constraint.constraint_id}:{type(exc).__name__}")
                passed = False
            if not passed:
                violation = ConstraintViolation(
                    constraint.constraint_id,
                    constraint.strength,
                    constraint.provenance,
                    constraint.description,
                )
                (hard if constraint.strength is ConstraintStrength.HARD else soft).append(violation)
        return ConstraintResult(
            admissible=not hard and not any(
                error.split(":", 1)[0] in {c.constraint_id for c in self.constraints if c.strength is ConstraintStrength.HARD}
                for error in errors
            ),
            hard_violations=tuple(hard),
            soft_violations=tuple(soft),
            evaluation_errors=tuple(errors),
        )


@dataclass(frozen=True)
class ConstraintConflict:
    left_id: str
    right_id: str
    explanation: str
    provenance: tuple[str, str]


def explain_conflict(left: Constraint[object], right: Constraint[object], explanation: str) -> ConstraintConflict:
    if left.constraint_id == right.constraint_id:
        raise ValueError("conflict requires distinct constraints")
    if not explanation or explanation.strip() != explanation:
        raise ValueError("conflict explanation must be explicit")
    return ConstraintConflict(
        left.constraint_id,
        right.constraint_id,
        explanation,
        (left.provenance, right.provenance),
    )
