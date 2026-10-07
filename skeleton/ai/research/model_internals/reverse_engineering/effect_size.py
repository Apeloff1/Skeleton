"""Effect-size estimation for controlled scalar reverse-engineering measurements."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ScalarMeasurement:
    measurement_id: str
    group: str
    value: float

    def __post_init__(self) -> None:
        if not self.measurement_id or not self.group:
            raise ReverseEngineeringError("scalar measurement identity is required")
        if not isfinite(self.value):
            raise ReverseEngineeringError("scalar measurement value must be finite")


@dataclass(frozen=True)
class EffectSizeReport:
    control_group: str
    treatment_group: str
    control_count: int
    treatment_count: int
    control_mean: float
    treatment_mean: float
    mean_difference: float
    pooled_standard_deviation: float
    standardized_effect: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "control_group": self.control_group,
            "treatment_group": self.treatment_group,
            "control_count": self.control_count,
            "treatment_count": self.treatment_count,
            "control_mean": self.control_mean,
            "treatment_mean": self.treatment_mean,
            "mean_difference": self.mean_difference,
            "pooled_standard_deviation": self.pooled_standard_deviation,
            "standardized_effect": self.standardized_effect,
            "digest": self.digest,
        }


def _sample_variance(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def estimate_effect_size(
    measurements: Sequence[ScalarMeasurement],
    *,
    control_group: str,
    treatment_group: str,
) -> EffectSizeReport:
    if control_group == treatment_group:
        raise ReverseEngineeringError("control_group and treatment_group must differ")
    ids = [item.measurement_id for item in measurements]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("measurement ids must be unique")
    control = [item.value for item in measurements if item.group == control_group]
    treatment = [item.value for item in measurements if item.group == treatment_group]
    if not control or not treatment:
        raise ReverseEngineeringError("both control and treatment groups require measurements")
    control_mean = sum(control) / len(control)
    treatment_mean = sum(treatment) / len(treatment)
    control_var = _sample_variance(control)
    treatment_var = _sample_variance(treatment)
    degrees = len(control) + len(treatment) - 2
    pooled_variance = (
        ((len(control) - 1) * control_var + (len(treatment) - 1) * treatment_var) / degrees
        if degrees > 0
        else 0.0
    )
    pooled_sd = sqrt(pooled_variance)
    difference = treatment_mean - control_mean
    standardized = difference / pooled_sd if pooled_sd > 0.0 else None
    payload = {
        "control_group": control_group,
        "treatment_group": treatment_group,
        "measurements": [
            {
                "measurement_id": item.measurement_id,
                "group": item.group,
                "value": item.value,
            }
            for item in sorted(measurements, key=lambda value: value.measurement_id)
            if item.group in {control_group, treatment_group}
        ],
    }
    return EffectSizeReport(
        control_group=control_group,
        treatment_group=treatment_group,
        control_count=len(control),
        treatment_count=len(treatment),
        control_mean=control_mean,
        treatment_mean=treatment_mean,
        mean_difference=difference,
        pooled_standard_deviation=pooled_sd,
        standardized_effect=standardized,
        digest=stable_digest(payload),
    )
