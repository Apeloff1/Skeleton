"""Specificity metrics for targeted versus off-target intervention effects."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class SpecificityObservation:
    observation_id: str
    target_id: str
    measured_id: str
    effect: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.target_id or not self.measured_id:
            raise ReverseEngineeringError("specificity observation identity is required")
        if not isfinite(self.effect):
            raise ReverseEngineeringError("specificity effect must be finite")

    @property
    def on_target(self) -> bool:
        return self.target_id == self.measured_id


@dataclass(frozen=True)
class InterventionSpecificityReport:
    observation_count: int
    on_target_count: int
    off_target_count: int
    mean_absolute_on_target_effect: float | None
    mean_absolute_off_target_effect: float | None
    specificity_ratio: float | None
    max_absolute_off_target_effect: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "on_target_count": self.on_target_count,
            "off_target_count": self.off_target_count,
            "mean_absolute_on_target_effect": self.mean_absolute_on_target_effect,
            "mean_absolute_off_target_effect": self.mean_absolute_off_target_effect,
            "specificity_ratio": self.specificity_ratio,
            "max_absolute_off_target_effect": self.max_absolute_off_target_effect,
            "digest": self.digest,
        }


def analyze_intervention_specificity(
    observations: Sequence[SpecificityObservation],
) -> InterventionSpecificityReport:
    if not observations:
        raise ReverseEngineeringError("intervention specificity requires observations")
    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("specificity observation ids must be unique")
    on_target = [abs(item.effect) for item in observations if item.on_target]
    off_target = [abs(item.effect) for item in observations if not item.on_target]
    mean_on = sum(on_target) / len(on_target) if on_target else None
    mean_off = sum(off_target) / len(off_target) if off_target else None
    ratio = None
    if mean_on is not None and mean_off is not None and mean_off > 0.0:
        ratio = mean_on / mean_off
    payload = {
        "observations": [
            {
                "observation_id": item.observation_id,
                "target_id": item.target_id,
                "measured_id": item.measured_id,
                "effect": item.effect,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ]
    }
    return InterventionSpecificityReport(
        observation_count=len(observations),
        on_target_count=len(on_target),
        off_target_count=len(off_target),
        mean_absolute_on_target_effect=mean_on,
        mean_absolute_off_target_effect=mean_off,
        specificity_ratio=ratio,
        max_absolute_off_target_effect=max(off_target) if off_target else 0.0,
        digest=stable_digest(payload),
    )
