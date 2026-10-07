"""Calibration quality across groups/environments."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class GroupCalibrationPrediction:
    prediction_id: str
    group_id: str
    probability: float
    outcome: bool

    def __post_init__(self) -> None:
        if not self.prediction_id or not self.group_id:
            raise ReverseEngineeringError("group calibration identity is required")
        if not isfinite(self.probability) or not 0.0 <= self.probability <= 1.0:
            raise ReverseEngineeringError("probability must be within [0, 1]")


@dataclass(frozen=True)
class GroupCalibrationMetric:
    group_id: str
    count: int
    mean_probability: float
    observed_rate: float
    absolute_gap: float
    brier_score: float


@dataclass(frozen=True)
class HierarchicalCalibrationReport:
    group_count: int
    prediction_count: int
    groups: tuple[GroupCalibrationMetric, ...]
    weighted_calibration_gap: float
    worst_group_gap: float
    worst_group_id: str
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_count": self.group_count,
            "prediction_count": self.prediction_count,
            "groups": [
                {
                    "group_id": item.group_id,
                    "count": item.count,
                    "mean_probability": item.mean_probability,
                    "observed_rate": item.observed_rate,
                    "absolute_gap": item.absolute_gap,
                    "brier_score": item.brier_score,
                }
                for item in self.groups
            ],
            "weighted_calibration_gap": self.weighted_calibration_gap,
            "worst_group_gap": self.worst_group_gap,
            "worst_group_id": self.worst_group_id,
            "digest": self.digest,
        }


def analyze_hierarchical_calibration(
    predictions: Sequence[GroupCalibrationPrediction],
) -> HierarchicalCalibrationReport:
    if not predictions:
        raise ReverseEngineeringError("hierarchical calibration requires predictions")
    ids = [item.prediction_id for item in predictions]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("prediction ids must be unique")
    grouped: dict[str, list[GroupCalibrationPrediction]] = {}
    for item in predictions:
        grouped.setdefault(item.group_id, []).append(item)

    metrics: list[GroupCalibrationMetric] = []
    weighted = 0.0
    for group_id, items in sorted(grouped.items()):
        mean_probability = sum(item.probability for item in items) / len(items)
        observed_rate = sum(item.outcome for item in items) / len(items)
        gap = abs(mean_probability - observed_rate)
        brier = sum(
            (item.probability - (1.0 if item.outcome else 0.0)) ** 2
            for item in items
        ) / len(items)
        metrics.append(
            GroupCalibrationMetric(
                group_id=group_id,
                count=len(items),
                mean_probability=mean_probability,
                observed_rate=observed_rate,
                absolute_gap=gap,
                brier_score=brier,
            )
        )
        weighted += gap * len(items)
    worst = max(metrics, key=lambda item: (item.absolute_gap, item.group_id))
    payload = {
        "predictions": [
            {
                "prediction_id": item.prediction_id,
                "group_id": item.group_id,
                "probability": item.probability,
                "outcome": item.outcome,
            }
            for item in sorted(predictions, key=lambda value: value.prediction_id)
        ]
    }
    return HierarchicalCalibrationReport(
        group_count=len(metrics),
        prediction_count=len(predictions),
        groups=tuple(metrics),
        weighted_calibration_gap=weighted / len(predictions),
        worst_group_gap=worst.absolute_gap,
        worst_group_id=worst.group_id,
        digest=stable_digest(payload),
    )
