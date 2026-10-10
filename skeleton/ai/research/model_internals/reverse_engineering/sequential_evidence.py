"""Sequential Bernoulli evidence accumulation with fail-closed thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class SequentialObservation:
    observation_id: str
    success: bool

    def __post_init__(self) -> None:
        if not self.observation_id:
            raise ReverseEngineeringError("sequential observation requires identity")


@dataclass(frozen=True)
class SequentialEvidenceReport:
    observation_count: int
    success_count: int
    success_rate: float
    log_likelihood_ratio: float
    decision: str
    boundary_crossing_index: int | None
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "success_count": self.success_count,
            "success_rate": self.success_rate,
            "log_likelihood_ratio": self.log_likelihood_ratio,
            "decision": self.decision,
            "boundary_crossing_index": self.boundary_crossing_index,
            "digest": self.digest,
        }


def analyze_sequential_evidence(
    observations: Sequence[SequentialObservation],
    *,
    null_success_probability: float = 0.5,
    alternative_success_probability: float = 0.8,
    accept_log_likelihood: float = 3.0,
    reject_log_likelihood: float = -3.0,
) -> SequentialEvidenceReport:
    if not observations:
        raise ReverseEngineeringError("sequential evidence requires observations")
    for value, name in (
        (null_success_probability, "null_success_probability"),
        (alternative_success_probability, "alternative_success_probability"),
    ):
        if not isfinite(value) or not 0.0 < value < 1.0:
            raise ReverseEngineeringError(f"{name} must be within (0, 1)")
    if alternative_success_probability == null_success_probability:
        raise ReverseEngineeringError("null and alternative probabilities must differ")
    if not isfinite(accept_log_likelihood) or not isfinite(reject_log_likelihood):
        raise ReverseEngineeringError("sequential boundaries must be finite")
    if reject_log_likelihood >= accept_log_likelihood:
        raise ReverseEngineeringError("reject boundary must be below accept boundary")

    ids = [item.observation_id for item in observations]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("sequential observation ids must be unique")

    llr = 0.0
    crossing: int | None = None
    decision = "continue"
    for index, item in enumerate(observations, start=1):
        if item.success:
            llr += log(alternative_success_probability / null_success_probability)
        else:
            llr += log(
                (1.0 - alternative_success_probability)
                / (1.0 - null_success_probability)
            )
        if crossing is None and llr >= accept_log_likelihood:
            crossing = index
            decision = "support"
        elif crossing is None and llr <= reject_log_likelihood:
            crossing = index
            decision = "reject"

    payload = {
        "observations": [
            {"observation_id": item.observation_id, "success": item.success}
            for item in observations
        ],
        "null_success_probability": null_success_probability,
        "alternative_success_probability": alternative_success_probability,
        "accept_log_likelihood": accept_log_likelihood,
        "reject_log_likelihood": reject_log_likelihood,
    }
    return SequentialEvidenceReport(
        observation_count=len(observations),
        success_count=sum(item.success for item in observations),
        success_rate=sum(item.success for item in observations) / len(observations),
        log_likelihood_ratio=llr,
        decision=decision,
        boundary_crossing_index=crossing,
        digest=stable_digest(payload),
    )
