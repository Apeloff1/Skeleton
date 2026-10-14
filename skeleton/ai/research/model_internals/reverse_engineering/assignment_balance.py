"""Balance diagnostics for randomized or stratified experiment assignments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class BalanceAssignment:
    unit_id: str
    arm: str
    stratum: str

    def __post_init__(self) -> None:
        if not self.unit_id or not self.arm or not self.stratum:
            raise ReverseEngineeringError("balance assignment identity is required")


@dataclass(frozen=True)
class AssignmentBalanceReport:
    arm_count: int
    stratum_count: int
    total_units: int
    maximum_stratum_arm_count_difference: int
    perfectly_balanced_strata: int
    all_strata_within_one: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm_count": self.arm_count,
            "stratum_count": self.stratum_count,
            "total_units": self.total_units,
            "maximum_stratum_arm_count_difference": self.maximum_stratum_arm_count_difference,
            "perfectly_balanced_strata": self.perfectly_balanced_strata,
            "all_strata_within_one": self.all_strata_within_one,
            "digest": self.digest,
        }


def analyze_assignment_balance(
    assignments: Sequence[BalanceAssignment],
) -> AssignmentBalanceReport:
    if not assignments:
        raise ReverseEngineeringError("assignment balance requires assignments")
    ids = [item.unit_id for item in assignments]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("assignment unit ids must be unique")
    arms = sorted({item.arm for item in assignments})
    strata = sorted({item.stratum for item in assignments})
    counts: dict[str, dict[str, int]] = {
        stratum: {arm: 0 for arm in arms}
        for stratum in strata
    }
    for item in assignments:
        counts[item.stratum][item.arm] += 1
    differences = []
    perfect = 0
    for stratum in strata:
        values = list(counts[stratum].values())
        difference = max(values) - min(values)
        differences.append(difference)
        if difference == 0:
            perfect += 1
    payload = {
        "assignments": [
            {"unit_id": item.unit_id, "arm": item.arm, "stratum": item.stratum}
            for item in sorted(assignments, key=lambda value: value.unit_id)
        ]
    }
    maximum = max(differences)
    return AssignmentBalanceReport(
        arm_count=len(arms),
        stratum_count=len(strata),
        total_units=len(assignments),
        maximum_stratum_arm_count_difference=maximum,
        perfectly_balanced_strata=perfect,
        all_strata_within_one=maximum <= 1,
        digest=stable_digest(payload),
    )
