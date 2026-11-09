"""Hierarchical uncertainty summaries across groups and replications."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class HierarchicalObservation:
    observation_id: str
    group_id: str
    value: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.group_id:
            raise ReverseEngineeringError("hierarchical observation identity is required")
        if not isfinite(self.value):
            raise ReverseEngineeringError("hierarchical observation value must be finite")


@dataclass(frozen=True)
class HierarchicalUncertaintyReport:
    group_count: int
    observation_count: int
    grand_mean: float
    within_group_variance: float
    between_group_variance: float
    total_variance: float
    intraclass_correlation: float | None
    standard_error_of_grand_mean: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_count": self.group_count,
            "observation_count": self.observation_count,
            "grand_mean": self.grand_mean,
            "within_group_variance": self.within_group_variance,
            "between_group_variance": self.between_group_variance,
            "total_variance": self.total_variance,
            "intraclass_correlation": self.intraclass_correlation,
            "standard_error_of_grand_mean": self.standard_error_of_grand_mean,
            "digest": self.digest,
        }


def _sample_variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def analyze_hierarchical_uncertainty(
    observations: Sequence[HierarchicalObservation],
) -> HierarchicalUncertaintyReport:
    if len(observations) < 2:
        raise ReverseEngineeringError("hierarchical uncertainty requires at least two observations")
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("hierarchical observation ids must be unique")
    grouped: dict[str, list[float]] = {}
    for item in observations:
        grouped.setdefault(item.group_id, []).append(item.value)
    group_means = [sum(values) / len(values) for values in grouped.values()]
    grand = sum(item.value for item in observations) / len(observations)
    within_components = [
        _sample_variance(values)
        for values in grouped.values()
        if len(values) >= 2
    ]
    within = sum(within_components) / len(within_components) if within_components else 0.0
    between = _sample_variance(group_means)
    total = _sample_variance([item.value for item in observations])
    icc = between / (between + within) if (between + within) > 0.0 else None
    standard_error = sqrt(total / len(observations)) if total > 0.0 else 0.0
    payload = {
        "observations": [
            {
                "observation_id": item.observation_id,
                "group_id": item.group_id,
                "value": item.value,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ]
    }
    return HierarchicalUncertaintyReport(
        group_count=len(grouped),
        observation_count=len(observations),
        grand_mean=grand,
        within_group_variance=within,
        between_group_variance=between,
        total_variance=total,
        intraclass_correlation=icc,
        standard_error_of_grand_mean=standard_error,
        digest=stable_digest(payload),
    )
