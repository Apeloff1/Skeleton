"""Observed-sample audit against predeclared experiment power requirements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class PowerRequirement:
    experiment_id: str
    required_per_group: int
    observed_group_counts: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ReverseEngineeringError("power requirement requires experiment_id")
        if self.required_per_group < 1:
            raise ReverseEngineeringError("required_per_group must be positive")
        names = [name for name, _ in self.observed_group_counts]
        if len(names) < 2 or len(names) != len(set(names)):
            raise ReverseEngineeringError("power audit requires at least two unique groups")
        if any(not name or count < 0 for name, count in self.observed_group_counts):
            raise ReverseEngineeringError("power group counts must be non-negative")


@dataclass(frozen=True)
class PowerAuditItem:
    experiment_id: str
    minimum_observed_group_count: int
    required_per_group: int
    powered: bool
    deficit: int


@dataclass(frozen=True)
class PowerAuditReport:
    experiment_count: int
    powered_count: int
    underpowered_count: int
    items: tuple[PowerAuditItem, ...]
    all_powered: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiment_count": self.experiment_count,
            "powered_count": self.powered_count,
            "underpowered_count": self.underpowered_count,
            "items": [
                {
                    "experiment_id": item.experiment_id,
                    "minimum_observed_group_count": item.minimum_observed_group_count,
                    "required_per_group": item.required_per_group,
                    "powered": item.powered,
                    "deficit": item.deficit,
                }
                for item in self.items
            ],
            "all_powered": self.all_powered,
            "digest": self.digest,
        }


def audit_experiment_power(
    requirements: Sequence[PowerRequirement],
) -> PowerAuditReport:
    if not requirements:
        raise ReverseEngineeringError("power audit requires requirements")
    ids = [item.experiment_id for item in requirements]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("power requirement experiment ids must be unique")
    items: list[PowerAuditItem] = []
    for requirement in sorted(requirements, key=lambda value: value.experiment_id):
        minimum = min(count for _, count in requirement.observed_group_counts)
        deficit = max(0, requirement.required_per_group - minimum)
        items.append(
            PowerAuditItem(
                experiment_id=requirement.experiment_id,
                minimum_observed_group_count=minimum,
                required_per_group=requirement.required_per_group,
                powered=deficit == 0,
                deficit=deficit,
            )
        )
    payload = {
        "requirements": [
            {
                "experiment_id": item.experiment_id,
                "required_per_group": item.required_per_group,
                "observed_group_counts": [list(pair) for pair in item.observed_group_counts],
            }
            for item in sorted(requirements, key=lambda value: value.experiment_id)
        ]
    }
    powered = sum(item.powered for item in items)
    return PowerAuditReport(
        experiment_count=len(items),
        powered_count=powered,
        underpowered_count=len(items) - powered,
        items=tuple(items),
        all_powered=powered == len(items),
        digest=stable_digest(payload),
    )
