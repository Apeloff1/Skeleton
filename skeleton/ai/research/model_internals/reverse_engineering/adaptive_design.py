"""Adaptive next-experiment selection from uncertainty, value, cost, and risk."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class AdaptiveExperimentCandidate:
    experiment_id: str
    domain: str
    uncertainty: float
    expected_information_gain: float
    estimated_cost: float
    risk: float = 0.0
    prerequisite_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.experiment_id or not self.domain:
            raise ReverseEngineeringError("adaptive experiment identity is required")
        for value, name in (
            (self.uncertainty, "uncertainty"),
            (self.expected_information_gain, "expected_information_gain"),
            (self.estimated_cost, "estimated_cost"),
            (self.risk, "risk"),
        ):
            if not isfinite(value) or value < 0.0:
                raise ReverseEngineeringError(f"{name} must be finite and non-negative")
        if self.estimated_cost <= 0.0:
            raise ReverseEngineeringError("estimated_cost must be positive")
        if len(self.prerequisite_ids) != len(set(self.prerequisite_ids)):
            raise ReverseEngineeringError("adaptive prerequisites must be unique")
        if self.experiment_id in self.prerequisite_ids:
            raise ReverseEngineeringError("experiment cannot depend on itself")

    @property
    def utility(self) -> float:
        return (
            self.uncertainty
            * self.expected_information_gain
            / self.estimated_cost
            / (1.0 + self.risk)
        )


@dataclass(frozen=True)
class AdaptiveDesignDecision:
    selected_ids: tuple[str, ...]
    deferred_ids: tuple[str, ...]
    total_cost: float
    total_expected_information_gain: float
    covered_domains: tuple[str, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_ids": list(self.selected_ids),
            "deferred_ids": list(self.deferred_ids),
            "total_cost": self.total_cost,
            "total_expected_information_gain": self.total_expected_information_gain,
            "covered_domains": list(self.covered_domains),
            "digest": self.digest,
        }


def select_adaptive_experiments(
    candidates: Sequence[AdaptiveExperimentCandidate],
    *,
    budget: float,
    completed_ids: Sequence[str] = (),
) -> AdaptiveDesignDecision:
    if not candidates:
        raise ReverseEngineeringError("adaptive design requires candidates")
    if not isfinite(budget) or budget <= 0.0:
        raise ReverseEngineeringError("budget must be finite and positive")
    ids = [item.experiment_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("candidate experiment ids must be unique")
    known = set(ids) | set(completed_ids)
    for item in candidates:
        missing = set(item.prerequisite_ids) - known
        if missing:
            raise ReverseEngineeringError(
                f"experiment {item.experiment_id!r} has unknown prerequisites"
            )

    ordered = sorted(candidates, key=lambda item: (-item.utility, item.experiment_id))
    selected: list[AdaptiveExperimentCandidate] = []
    selected_ids = set(completed_ids)
    spent = 0.0
    remaining = list(ordered)
    progress = True
    while progress and remaining:
        progress = False
        next_remaining: list[AdaptiveExperimentCandidate] = []
        for item in remaining:
            if not set(item.prerequisite_ids).issubset(selected_ids):
                next_remaining.append(item)
                continue
            if spent + item.estimated_cost <= budget + 1e-12:
                selected.append(item)
                selected_ids.add(item.experiment_id)
                spent += item.estimated_cost
                progress = True
            else:
                next_remaining.append(item)
        remaining = next_remaining

    chosen = tuple(item.experiment_id for item in selected)
    deferred = tuple(sorted(item.experiment_id for item in candidates if item.experiment_id not in set(chosen)))
    payload = {
        "budget": budget,
        "completed_ids": sorted(set(completed_ids)),
        "candidates": [
            {
                "experiment_id": item.experiment_id,
                "domain": item.domain,
                "uncertainty": item.uncertainty,
                "expected_information_gain": item.expected_information_gain,
                "estimated_cost": item.estimated_cost,
                "risk": item.risk,
                "prerequisite_ids": list(item.prerequisite_ids),
            }
            for item in sorted(candidates, key=lambda value: value.experiment_id)
        ],
        "selected_ids": list(chosen),
    }
    return AdaptiveDesignDecision(
        selected_ids=chosen,
        deferred_ids=deferred,
        total_cost=spent,
        total_expected_information_gain=sum(item.expected_information_gain for item in selected),
        covered_domains=tuple(sorted({item.domain for item in selected})),
        digest=stable_digest(payload),
    )
