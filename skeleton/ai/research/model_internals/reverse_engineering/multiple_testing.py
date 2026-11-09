"""Benjamini-Hochberg false-discovery-rate correction."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class HypothesisPValue:
    hypothesis_id: str
    p_value: float

    def __post_init__(self) -> None:
        if not self.hypothesis_id:
            raise ReverseEngineeringError("hypothesis id is required")
        if not isfinite(self.p_value) or not 0.0 <= self.p_value <= 1.0:
            raise ReverseEngineeringError("p_value must be within [0, 1]")


@dataclass(frozen=True)
class AdjustedHypothesis:
    hypothesis_id: str
    p_value: float
    adjusted_p_value: float
    rejected: bool


@dataclass(frozen=True)
class MultipleTestingReport:
    hypothesis_count: int
    alpha: float
    rejected_count: int
    adjusted: tuple[AdjustedHypothesis, ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_count": self.hypothesis_count,
            "alpha": self.alpha,
            "rejected_count": self.rejected_count,
            "adjusted": [
                {
                    "hypothesis_id": item.hypothesis_id,
                    "p_value": item.p_value,
                    "adjusted_p_value": item.adjusted_p_value,
                    "rejected": item.rejected,
                }
                for item in self.adjusted
            ],
            "digest": self.digest,
        }


def benjamini_hochberg(
    hypotheses: Sequence[HypothesisPValue],
    *,
    alpha: float = 0.05,
) -> MultipleTestingReport:
    if not hypotheses:
        raise ReverseEngineeringError("multiple testing correction requires hypotheses")
    if not isfinite(alpha) or not 0.0 < alpha < 1.0:
        raise ReverseEngineeringError("alpha must be within (0, 1)")
    ids = [item.hypothesis_id for item in hypotheses]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("hypothesis ids must be unique")
    ordered = sorted(hypotheses, key=lambda item: (item.p_value, item.hypothesis_id))
    m = len(ordered)
    raw_adjusted = [
        min(1.0, item.p_value * m / rank)
        for rank, item in enumerate(ordered, start=1)
    ]
    monotone = list(raw_adjusted)
    for index in range(m - 2, -1, -1):
        monotone[index] = min(monotone[index], monotone[index + 1])
    adjusted = tuple(
        AdjustedHypothesis(
            hypothesis_id=item.hypothesis_id,
            p_value=item.p_value,
            adjusted_p_value=monotone[index],
            rejected=monotone[index] <= alpha,
        )
        for index, item in enumerate(ordered)
    )
    payload = {
        "alpha": alpha,
        "hypotheses": [
            {"hypothesis_id": item.hypothesis_id, "p_value": item.p_value}
            for item in ordered
        ],
    }
    return MultipleTestingReport(
        hypothesis_count=m,
        alpha=alpha,
        rejected_count=sum(item.rejected for item in adjusted),
        adjusted=adjusted,
        digest=stable_digest(payload),
    )
