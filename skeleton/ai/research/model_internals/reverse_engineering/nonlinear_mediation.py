"""Dose-stratified nonlinear mediation summaries."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class NonlinearMediationObservation:
    observation_id: str
    probe_digest: str
    dose: float
    treatment: bool
    mediator_blocked: bool
    outcome: float

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("nonlinear mediation observation requires identity")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be sha256 hex")
        if not isfinite(self.dose) or self.dose < 0.0:
            raise ReverseEngineeringError("dose must be finite and non-negative")
        if not isfinite(self.outcome):
            raise ReverseEngineeringError("outcome must be finite")


@dataclass(frozen=True)
class NonlinearMediationPoint:
    dose: float
    total_effect: float
    direct_effect: float
    mediated_effect: float
    mediated_fraction: float | None


@dataclass(frozen=True)
class NonlinearMediationReport:
    dose_count: int
    points: tuple[NonlinearMediationPoint, ...]
    mediated_effect_monotonicity_violations: int
    peak_mediated_dose: float
    peak_absolute_mediated_effect: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "dose_count": self.dose_count,
            "points": [
                {
                    "dose": point.dose,
                    "total_effect": point.total_effect,
                    "direct_effect": point.direct_effect,
                    "mediated_effect": point.mediated_effect,
                    "mediated_fraction": point.mediated_fraction,
                }
                for point in self.points
            ],
            "mediated_effect_monotonicity_violations": self.mediated_effect_monotonicity_violations,
            "peak_mediated_dose": self.peak_mediated_dose,
            "peak_absolute_mediated_effect": self.peak_absolute_mediated_effect,
            "digest": self.digest,
        }


def analyze_nonlinear_mediation(
    observations: Sequence[NonlinearMediationObservation],
) -> NonlinearMediationReport:
    if not observations:
        raise ReverseEngineeringError("nonlinear mediation requires observations")
    digests = {item.probe_digest for item in observations}
    if len(digests) != 1:
        raise ReverseEngineeringError("nonlinear mediation observations must share probe_digest")
    grouped: dict[float, list[NonlinearMediationObservation]] = {}
    for item in observations:
        grouped.setdefault(item.dose, []).append(item)

    points: list[NonlinearMediationPoint] = []
    for dose, items in sorted(grouped.items()):
        controls = [item.outcome for item in items if not item.treatment and not item.mediator_blocked]
        treated = [item.outcome for item in items if item.treatment and not item.mediator_blocked]
        blocked = [item.outcome for item in items if item.treatment and item.mediator_blocked]
        if not controls or not treated or not blocked:
            raise ReverseEngineeringError(
                f"dose {dose!r} requires control, treatment, and treatment+blocked observations"
            )
        control_mean = sum(controls) / len(controls)
        treatment_mean = sum(treated) / len(treated)
        blocked_mean = sum(blocked) / len(blocked)
        total = treatment_mean - control_mean
        direct = blocked_mean - control_mean
        mediated = treatment_mean - blocked_mean
        points.append(
            NonlinearMediationPoint(
                dose=dose,
                total_effect=total,
                direct_effect=direct,
                mediated_effect=mediated,
                mediated_fraction=(mediated / total if total != 0.0 else None),
            )
        )

    violations = 0
    absolute_effects = [abs(point.mediated_effect) for point in points]
    for left, right in zip(absolute_effects, absolute_effects[1:]):
        if right + 1e-12 < left:
            violations += 1
    peak = max(points, key=lambda point: (abs(point.mediated_effect), point.dose))
    payload = {
        "probe_digest": next(iter(digests)),
        "observations": [
            {
                "observation_id": item.observation_id,
                "dose": item.dose,
                "treatment": item.treatment,
                "mediator_blocked": item.mediator_blocked,
                "outcome": item.outcome,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ],
    }
    return NonlinearMediationReport(
        dose_count=len(points),
        points=tuple(points),
        mediated_effect_monotonicity_violations=violations,
        peak_mediated_dose=peak.dose,
        peak_absolute_mediated_effect=abs(peak.mediated_effect),
        digest=stable_digest(payload),
    )
