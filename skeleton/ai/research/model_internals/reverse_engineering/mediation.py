"""Controlled mediation summaries for scalar causal experiments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class MediationObservation:
    observation_id: str
    probe_digest: str
    treatment: bool
    mediator_blocked: bool
    outcome: float

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("mediation observation requires identity")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if not isfinite(self.outcome):
            raise ReverseEngineeringError("mediation outcome must be finite")


@dataclass(frozen=True)
class MediationReport:
    observation_count: int
    control_mean: float
    treatment_mean: float
    treatment_blocked_mean: float
    total_effect: float
    direct_effect: float
    mediated_effect: float
    mediated_fraction: float | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "control_mean": self.control_mean,
            "treatment_mean": self.treatment_mean,
            "treatment_blocked_mean": self.treatment_blocked_mean,
            "total_effect": self.total_effect,
            "direct_effect": self.direct_effect,
            "mediated_effect": self.mediated_effect,
            "mediated_fraction": self.mediated_fraction,
            "digest": self.digest,
        }


def analyze_mediation(
    observations: Sequence[MediationObservation],
) -> MediationReport:
    if not observations:
        raise ReverseEngineeringError("mediation analysis requires observations")
    probe_digests = {item.probe_digest for item in observations}
    if len(probe_digests) != 1:
        raise ReverseEngineeringError("mediation observations must share probe_digest")

    controls = [
        item.outcome
        for item in observations
        if not item.treatment and not item.mediator_blocked
    ]
    treated = [
        item.outcome
        for item in observations
        if item.treatment and not item.mediator_blocked
    ]
    blocked = [
        item.outcome
        for item in observations
        if item.treatment and item.mediator_blocked
    ]
    if not controls or not treated or not blocked:
        raise ReverseEngineeringError(
            "mediation analysis requires control, treatment, and treatment+blocked groups"
        )
    control_mean = sum(controls) / len(controls)
    treatment_mean = sum(treated) / len(treated)
    blocked_mean = sum(blocked) / len(blocked)
    total = treatment_mean - control_mean
    direct = blocked_mean - control_mean
    mediated = treatment_mean - blocked_mean
    fraction = mediated / total if total != 0.0 else None
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "observations": [
            {
                "observation_id": item.observation_id,
                "treatment": item.treatment,
                "mediator_blocked": item.mediator_blocked,
                "outcome": item.outcome,
            }
            for item in sorted(observations, key=lambda value: value.observation_id)
        ],
    }
    return MediationReport(
        observation_count=len(observations),
        control_mean=control_mean,
        treatment_mean=treatment_mean,
        treatment_blocked_mean=blocked_mean,
        total_effect=total,
        direct_effect=direct,
        mediated_effect=mediated,
        mediated_fraction=fraction,
        digest=stable_digest(payload),
    )
