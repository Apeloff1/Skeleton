"""Negative-control checks for leakage and false-positive reverse-engineering signals."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class NegativeControlObservation:
    observation_id: str
    control_class: str
    expected_effect: float
    observed_effect: float
    tolerance: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.control_class:
            raise ReverseEngineeringError("negative-control identity is required")
        if any(
            not isfinite(value)
            for value in (self.expected_effect, self.observed_effect, self.tolerance)
        ):
            raise ReverseEngineeringError("negative-control values must be finite")
        if self.tolerance < 0.0:
            raise ReverseEngineeringError("negative-control tolerance must be non-negative")

    @property
    def deviation(self) -> float:
        return abs(self.observed_effect - self.expected_effect)

    @property
    def passes(self) -> bool:
        return self.deviation <= self.tolerance


@dataclass(frozen=True)
class NegativeControlReport:
    observation_count: int
    passing_count: int
    failing_count: int
    pass_ratio: float
    mean_deviation: float
    max_deviation: float
    leak_suspected: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "passing_count": self.passing_count,
            "failing_count": self.failing_count,
            "pass_ratio": self.pass_ratio,
            "mean_deviation": self.mean_deviation,
            "max_deviation": self.max_deviation,
            "leak_suspected": self.leak_suspected,
            "digest": self.digest,
        }


def analyze_negative_controls(
    observations: Sequence[NegativeControlObservation],
    *,
    minimum_pass_ratio: float = 0.9,
) -> NegativeControlReport:
    if not observations:
        raise ReverseEngineeringError("negative-control analysis requires observations")
    if not isfinite(minimum_pass_ratio) or not 0.0 <= minimum_pass_ratio <= 1.0:
        raise ReverseEngineeringError("minimum_pass_ratio must be within [0, 1]")
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("negative-control observation ids must be unique")
    passing = sum(item.passes for item in observations)
    deviations = [item.deviation for item in observations]
    pass_ratio = passing / len(observations)
    payload = {
        "minimum_pass_ratio": minimum_pass_ratio,
        "observations": [
            {
                "observation_id": item.observation_id,
                "control_class": item.control_class,
                "expected_effect": item.expected_effect,
                "observed_effect": item.observed_effect,
                "tolerance": item.tolerance,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ],
    }
    return NegativeControlReport(
        observation_count=len(observations),
        passing_count=passing,
        failing_count=len(observations) - passing,
        pass_ratio=pass_ratio,
        mean_deviation=sum(deviations) / len(deviations),
        max_deviation=max(deviations),
        leak_suspected=pass_ratio < minimum_pass_ratio,
        digest=stable_digest(payload),
    )
