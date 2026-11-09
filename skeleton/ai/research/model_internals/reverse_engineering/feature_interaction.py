"""Pairwise feature-interaction/synergy summaries for authorized interventions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class FeatureInteractionObservation:
    observation_id: str
    probe_digest: str
    feature_a: str
    feature_b: str
    baseline: float
    effect_a: float
    effect_b: float
    joint_effect: float

    def __post_init__(self) -> None:
        if not self.observation_id or not self.feature_a or not self.feature_b:
            raise ReverseEngineeringError("feature interaction identity is required")
        if self.feature_a == self.feature_b:
            raise ReverseEngineeringError("feature interaction requires distinct features")
        if not is_sha256_digest(self.probe_digest):
            raise ReverseEngineeringError("probe_digest must be a sha256 hex digest")
        if any(
            not isfinite(value)
            for value in (self.baseline, self.effect_a, self.effect_b, self.joint_effect)
        ):
            raise ReverseEngineeringError("feature interaction values must be finite")

    @property
    def synergy(self) -> float:
        additive_prediction = self.baseline + (self.effect_a - self.baseline) + (self.effect_b - self.baseline)
        return self.joint_effect - additive_prediction


@dataclass(frozen=True)
class FeatureInteractionReport:
    feature_a: str
    feature_b: str
    observation_count: int
    mean_synergy: float
    mean_absolute_synergy: float
    positive_synergy_ratio: float
    sign_consistency: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_a": self.feature_a,
            "feature_b": self.feature_b,
            "observation_count": self.observation_count,
            "mean_synergy": self.mean_synergy,
            "mean_absolute_synergy": self.mean_absolute_synergy,
            "positive_synergy_ratio": self.positive_synergy_ratio,
            "sign_consistency": self.sign_consistency,
            "digest": self.digest,
        }


def analyze_feature_interactions(
    observations: Sequence[FeatureInteractionObservation],
) -> tuple[FeatureInteractionReport, ...]:
    if not observations:
        raise ReverseEngineeringError("feature interaction analysis requires observations")
    grouped: dict[tuple[str, str], list[FeatureInteractionObservation]] = {}
    for item in observations:
        key = tuple(sorted((item.feature_a, item.feature_b)))
        grouped.setdefault(key, []).append(item)

    reports: list[FeatureInteractionReport] = []
    for (feature_a, feature_b), items in sorted(grouped.items()):
        probe_digests = {item.probe_digest for item in items}
        if len(probe_digests) != 1:
            raise ReverseEngineeringError("feature interaction group must share probe_digest")
        synergies = [item.synergy for item in items]
        mean = sum(synergies) / len(synergies)
        if mean > 0:
            consistency = sum(value > 0 for value in synergies) / len(synergies)
        elif mean < 0:
            consistency = sum(value < 0 for value in synergies) / len(synergies)
        else:
            consistency = sum(value == 0 for value in synergies) / len(synergies)
        payload = {
            "probe_digest": next(iter(probe_digests)),
            "feature_a": feature_a,
            "feature_b": feature_b,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "baseline": item.baseline,
                    "effect_a": item.effect_a,
                    "effect_b": item.effect_b,
                    "joint_effect": item.joint_effect,
                }
                for item in sorted(items, key=lambda value: value.observation_id)
            ],
        }
        reports.append(
            FeatureInteractionReport(
                feature_a=feature_a,
                feature_b=feature_b,
                observation_count=len(items),
                mean_synergy=mean,
                mean_absolute_synergy=sum(abs(value) for value in synergies) / len(synergies),
                positive_synergy_ratio=sum(value > 0 for value in synergies) / len(synergies),
                sign_consistency=consistency,
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
