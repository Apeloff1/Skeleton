"""Feature/unit specialization summaries for authorized local-model probes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class FeatureUnitObservation:
    observation_id: str
    feature_digest: str
    layer_id: str
    unit_id: str
    score: float
    input_digest: str

    def __post_init__(self) -> None:
        if not self.observation_id or not self.layer_id or not self.unit_id:
            raise ReverseEngineeringError("feature/unit observation identity is required")
        if not is_sha256_digest(self.feature_digest) or not is_sha256_digest(self.input_digest):
            raise ReverseEngineeringError("feature/unit digests must be sha256 hex digests")
        if not isfinite(self.score):
            raise ReverseEngineeringError("feature/unit score must be finite")


@dataclass(frozen=True)
class FeatureSpecializationReport:
    feature_digest: str
    observation_count: int
    layer_count: int
    unit_count: int
    top_layer_id: str
    top_unit_id: str
    top_mean_score: float
    score_concentration: float
    positive_unit_ratio: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_digest": self.feature_digest,
            "observation_count": self.observation_count,
            "layer_count": self.layer_count,
            "unit_count": self.unit_count,
            "top_layer_id": self.top_layer_id,
            "top_unit_id": self.top_unit_id,
            "top_mean_score": self.top_mean_score,
            "score_concentration": self.score_concentration,
            "positive_unit_ratio": self.positive_unit_ratio,
            "digest": self.digest,
        }


def analyze_feature_specialization(
    observations: Sequence[FeatureUnitObservation],
) -> tuple[FeatureSpecializationReport, ...]:
    if not observations:
        raise ReverseEngineeringError("feature specialization requires observations")
    grouped: dict[str, list[FeatureUnitObservation]] = {}
    for observation in observations:
        grouped.setdefault(observation.feature_digest, []).append(observation)

    reports: list[FeatureSpecializationReport] = []
    for feature_digest, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.observation_id)
        unit_scores: dict[tuple[str, str], list[float]] = {}
        for item in ordered:
            unit_scores.setdefault((item.layer_id, item.unit_id), []).append(item.score)
        unit_means = {
            key: sum(values) / len(values)
            for key, values in unit_scores.items()
        }
        top_key, top_score = max(
            unit_means.items(),
            key=lambda item: (item[1], item[0][0], item[0][1]),
        )
        absolute = [abs(score) for score in unit_means.values()]
        total_abs = sum(absolute)
        concentration = abs(top_score) / total_abs if total_abs else 0.0
        payload = {
            "feature_digest": feature_digest,
            "observations": [
                {
                    "observation_id": item.observation_id,
                    "layer_id": item.layer_id,
                    "unit_id": item.unit_id,
                    "score": item.score,
                    "input_digest": item.input_digest,
                }
                for item in ordered
            ],
        }
        reports.append(
            FeatureSpecializationReport(
                feature_digest=feature_digest,
                observation_count=len(ordered),
                layer_count=len({item.layer_id for item in ordered}),
                unit_count=len(unit_means),
                top_layer_id=top_key[0],
                top_unit_id=top_key[1],
                top_mean_score=top_score,
                score_concentration=concentration,
                positive_unit_ratio=sum(score > 0.0 for score in unit_means.values()) / len(unit_means),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
