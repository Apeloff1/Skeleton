"""Equivalence checks for alternative interventions on matched probes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class InterventionEffectPair:
    pair_id: str
    probe_digest: str
    intervention_a: str
    intervention_b: str
    effect_a: float
    effect_b: float

    def __post_init__(self) -> None:
        if not self.pair_id or not self.intervention_a or not self.intervention_b:
            raise ReverseEngineeringError("intervention equivalence identity is required")
        if self.intervention_a == self.intervention_b:
            raise ReverseEngineeringError("interventions must be distinct")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be sha256 hex")
        if not isfinite(self.effect_a) or not isfinite(self.effect_b):
            raise ReverseEngineeringError("intervention effects must be finite")

    @property
    def difference(self) -> float:
        return self.effect_a - self.effect_b


@dataclass(frozen=True)
class InterventionEquivalenceReport:
    intervention_a: str
    intervention_b: str
    pair_count: int
    mean_difference: float
    mean_absolute_difference: float
    max_absolute_difference: float
    within_tolerance_ratio: float
    equivalent: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "intervention_a": self.intervention_a,
            "intervention_b": self.intervention_b,
            "pair_count": self.pair_count,
            "mean_difference": self.mean_difference,
            "mean_absolute_difference": self.mean_absolute_difference,
            "max_absolute_difference": self.max_absolute_difference,
            "within_tolerance_ratio": self.within_tolerance_ratio,
            "equivalent": self.equivalent,
            "digest": self.digest,
        }


def analyze_intervention_equivalence(
    pairs: Sequence[InterventionEffectPair],
    *,
    tolerance: float = 0.1,
    minimum_within_tolerance_ratio: float = 0.9,
) -> InterventionEquivalenceReport:
    if not pairs:
        raise ReverseEngineeringError("intervention equivalence requires pairs")
    if not isfinite(tolerance) or tolerance < 0.0:
        raise ReverseEngineeringError("tolerance must be finite and non-negative")
    if not 0.0 <= minimum_within_tolerance_ratio <= 1.0:
        raise ReverseEngineeringError("minimum_within_tolerance_ratio must be within [0, 1]")
    interventions = {
        tuple(sorted((pair.intervention_a, pair.intervention_b)))
        for pair in pairs
    }
    if len(interventions) != 1:
        raise ReverseEngineeringError("equivalence pairs must compare the same interventions")
    ids = [pair.pair_id for pair in pairs]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("equivalence pair ids must be unique")

    a, b = next(iter(interventions))
    canonical: list[tuple[str, str, float]] = []
    for pair in pairs:
        difference = pair.effect_a - pair.effect_b
        if pair.intervention_a != a:
            difference = -difference
        canonical.append((pair.pair_id, pair.probe_digest, difference))
    differences = [item[2] for item in canonical]
    absolute = [abs(value) for value in differences]
    ratio = sum(value <= tolerance for value in absolute) / len(absolute)
    payload = {
        "intervention_a": a,
        "intervention_b": b,
        "tolerance": tolerance,
        "minimum_within_tolerance_ratio": minimum_within_tolerance_ratio,
        "pairs": [
            {"pair_id": pair_id, "probe_digest": digest, "difference": difference}
            for pair_id, digest, difference in sorted(canonical)
        ],
    }
    return InterventionEquivalenceReport(
        intervention_a=a,
        intervention_b=b,
        pair_count=len(pairs),
        mean_difference=sum(differences) / len(differences),
        mean_absolute_difference=sum(absolute) / len(absolute),
        max_absolute_difference=max(absolute),
        within_tolerance_ratio=ratio,
        equivalent=ratio >= minimum_within_tolerance_ratio,
        digest=stable_digest(payload),
    )
