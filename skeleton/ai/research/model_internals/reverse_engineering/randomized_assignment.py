"""Deterministic balanced assignment for controlled characterization experiments."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class AssignmentUnit:
    unit_id: str
    stratum: str = "default"

    def __post_init__(self) -> None:
        if not self.unit_id or not self.stratum:
            raise ReverseEngineeringError("assignment unit identity is required")


@dataclass(frozen=True)
class AssignedUnit:
    unit_id: str
    stratum: str
    arm: str


@dataclass(frozen=True)
class AssignmentPlan:
    seed: int
    arms: tuple[str, ...]
    assignments: tuple[AssignedUnit, ...]
    per_stratum_counts: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "arms": list(self.arms),
            "assignments": [
                {"unit_id": item.unit_id, "stratum": item.stratum, "arm": item.arm}
                for item in self.assignments
            ],
            "per_stratum_counts": [
                [stratum, [list(pair) for pair in counts]]
                for stratum, counts in self.per_stratum_counts
            ],
            "digest": self.digest,
        }


def _rank(seed: int, stratum: str, unit_id: str) -> str:
    return sha256(f"{seed}\0{stratum}\0{unit_id}".encode()).hexdigest()


def build_balanced_assignment(
    units: Sequence[AssignmentUnit],
    arms: Sequence[str],
    *,
    seed: int = 0,
) -> AssignmentPlan:
    if not units:
        raise ReverseEngineeringError("assignment requires units")
    arm_tuple = tuple(arms)
    if len(arm_tuple) < 2 or any(not arm for arm in arm_tuple):
        raise ReverseEngineeringError("assignment requires at least two named arms")
    if len(arm_tuple) != len(set(arm_tuple)):
        raise ReverseEngineeringError("assignment arm names must be unique")
    ids = [unit.unit_id for unit in units]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("assignment unit ids must be unique")

    strata: dict[str, list[AssignmentUnit]] = {}
    for unit in units:
        strata.setdefault(unit.stratum, []).append(unit)

    assigned: list[AssignedUnit] = []
    summaries: list[tuple[str, tuple[tuple[str, int], ...]]] = []
    for stratum, items in sorted(strata.items()):
        ordered = sorted(items, key=lambda item: (_rank(seed, stratum, item.unit_id), item.unit_id))
        counts = {arm: 0 for arm in arm_tuple}
        for index, item in enumerate(ordered):
            arm = arm_tuple[index % len(arm_tuple)]
            counts[arm] += 1
            assigned.append(AssignedUnit(item.unit_id, stratum, arm))
        summaries.append((stratum, tuple(sorted(counts.items()))))

    assigned_tuple = tuple(sorted(assigned, key=lambda item: item.unit_id))
    payload = {
        "seed": seed,
        "arms": list(arm_tuple),
        "assignments": [
            {"unit_id": item.unit_id, "stratum": item.stratum, "arm": item.arm}
            for item in assigned_tuple
        ],
    }
    return AssignmentPlan(
        seed=seed,
        arms=arm_tuple,
        assignments=assigned_tuple,
        per_stratum_counts=tuple(summaries),
        digest=stable_digest(payload),
    )
