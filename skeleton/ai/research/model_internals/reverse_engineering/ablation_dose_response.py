"""Dose-response analysis for controlled ablations or interventions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class DoseResponseTrial:
    trial_id: str
    probe_digest: str
    dose: float
    metric: float

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise ReverseEngineeringError("dose-response trial requires identity")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be sha256 hex")
        if not isfinite(self.dose) or self.dose < 0.0:
            raise ReverseEngineeringError("dose must be finite and non-negative")
        if not isfinite(self.metric):
            raise ReverseEngineeringError("metric must be finite")


@dataclass(frozen=True)
class DoseResponseReport:
    trial_count: int
    min_dose: float
    max_dose: float
    baseline_metric: float
    terminal_metric: float
    total_change: float
    monotonic_direction: str
    monotonicity_violations: int
    mean_slope: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_count": self.trial_count,
            "min_dose": self.min_dose,
            "max_dose": self.max_dose,
            "baseline_metric": self.baseline_metric,
            "terminal_metric": self.terminal_metric,
            "total_change": self.total_change,
            "monotonic_direction": self.monotonic_direction,
            "monotonicity_violations": self.monotonicity_violations,
            "mean_slope": self.mean_slope,
            "digest": self.digest,
        }


def analyze_ablation_dose_response(
    trials: Sequence[DoseResponseTrial],
) -> DoseResponseReport:
    if len(trials) < 2:
        raise ReverseEngineeringError("dose-response analysis requires at least two trials")
    probe_digests = {trial.probe_digest for trial in trials}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("dose-response trials must share probe_digest")
    ordered = sorted(trials, key=lambda item: (item.dose, item.trial_id))
    doses = [item.dose for item in ordered]
    if len(doses) != len(set(doses)):
        raise ReverseEngineeringError("dose values must be unique")

    change = ordered[-1].metric - ordered[0].metric
    direction = "flat" if change == 0.0 else ("increasing" if change > 0.0 else "decreasing")
    slopes: list[float] = []
    violations = 0
    for left, right in zip(ordered, ordered[1:]):
        slope = (right.metric - left.metric) / (right.dose - left.dose)
        slopes.append(slope)
        if direction == "increasing" and slope < -1e-12:
            violations += 1
        elif direction == "decreasing" and slope > 1e-12:
            violations += 1
        elif direction == "flat" and abs(slope) > 1e-12:
            violations += 1

    payload = {
        "probe_digest": next(iter(probe_digests)),
        "trials": [
            {"trial_id": item.trial_id, "dose": item.dose, "metric": item.metric}
            for item in ordered
        ],
    }
    return DoseResponseReport(
        trial_count=len(ordered),
        min_dose=ordered[0].dose,
        max_dose=ordered[-1].dose,
        baseline_metric=ordered[0].metric,
        terminal_metric=ordered[-1].metric,
        total_change=change,
        monotonic_direction=direction,
        monotonicity_violations=violations,
        mean_slope=(sum(slopes) / len(slopes) if slopes else None),
        digest=stable_digest(payload),
    )
