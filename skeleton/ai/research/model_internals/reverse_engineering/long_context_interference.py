"""Long-context interference curves from controlled distractor-load experiments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class InterferenceTrial:
    trial_id: str
    probe_digest: str
    distractor_units: int
    target_position: int
    fidelity: float
    output_digest: str

    def __post_init__(self) -> None:
        if not self.trial_id:
            raise ReverseEngineeringError("interference trial requires identity")
        if not is_sha256_digest(self.probe_digest) or not is_sha256_digest(self.output_digest):
            raise ReverseEngineeringError("interference digests must be sha256 hex digests")
        if self.distractor_units < 0 or self.target_position < 0:
            raise ReverseEngineeringError("interference units and position must be non-negative")
        if not isfinite(self.fidelity) or not 0.0 <= self.fidelity <= 1.0:
            raise ReverseEngineeringError("fidelity must be finite and within [0, 1]")


@dataclass(frozen=True)
class InterferenceReport:
    trial_count: int
    min_distractor_units: int
    max_distractor_units: int
    baseline_fidelity: float
    terminal_fidelity: float
    fidelity_drop: float
    first_below_threshold_units: int | None
    monotonicity_violations: int
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_count": self.trial_count,
            "min_distractor_units": self.min_distractor_units,
            "max_distractor_units": self.max_distractor_units,
            "baseline_fidelity": self.baseline_fidelity,
            "terminal_fidelity": self.terminal_fidelity,
            "fidelity_drop": self.fidelity_drop,
            "first_below_threshold_units": self.first_below_threshold_units,
            "monotonicity_violations": self.monotonicity_violations,
            "digest": self.digest,
        }


def analyze_long_context_interference(
    trials: Sequence[InterferenceTrial],
    *,
    fidelity_threshold: float = 0.8,
) -> InterferenceReport:
    if not trials:
        raise ReverseEngineeringError("long-context interference requires trials")
    if not isfinite(fidelity_threshold) or not 0.0 <= fidelity_threshold <= 1.0:
        raise ReverseEngineeringError("fidelity_threshold must be within [0, 1]")
    probe_digests = {trial.probe_digest for trial in trials}
    positions = {trial.target_position for trial in trials}
    if len(probe_digests) != 1 or len(positions) != 1:
        raise ReverseEngineeringError("interference trials must share probe and target position")
    ordered = sorted(trials, key=lambda item: (item.distractor_units, item.trial_id))
    units = [item.distractor_units for item in ordered]
    if len(units) != len(set(units)):
        raise ReverseEngineeringError("distractor_units must be unique")
    violations = sum(
        right.fidelity > left.fidelity + 1e-12
        for left, right in zip(ordered, ordered[1:])
    )
    below = [
        item.distractor_units
        for item in ordered
        if item.fidelity < fidelity_threshold
    ]
    payload = {
        "probe_digest": next(iter(probe_digests)),
        "target_position": next(iter(positions)),
        "fidelity_threshold": fidelity_threshold,
        "trials": [
            {
                "trial_id": item.trial_id,
                "distractor_units": item.distractor_units,
                "fidelity": item.fidelity,
                "output_digest": item.output_digest,
            }
            for item in ordered
        ],
    }
    return InterferenceReport(
        trial_count=len(ordered),
        min_distractor_units=ordered[0].distractor_units,
        max_distractor_units=ordered[-1].distractor_units,
        baseline_fidelity=ordered[0].fidelity,
        terminal_fidelity=ordered[-1].fidelity,
        fidelity_drop=ordered[0].fidelity - ordered[-1].fidelity,
        first_below_threshold_units=min(below) if below else None,
        monotonicity_violations=violations,
        digest=stable_digest(payload),
    )
