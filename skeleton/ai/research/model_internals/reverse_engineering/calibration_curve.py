"""Binned probability calibration diagnostics for binary research predictions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class CalibrationPrediction:
    prediction_id: str
    probability: float
    outcome: bool

    def __post_init__(self) -> None:
        if not self.prediction_id:
            raise ReverseEngineeringError("calibration prediction requires identity")
        if not isfinite(self.probability) or not 0.0 <= self.probability <= 1.0:
            raise ReverseEngineeringError("probability must be within [0, 1]")


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_probability: float
    observed_rate: float
    absolute_gap: float


@dataclass(frozen=True)
class CalibrationCurveReport:
    prediction_count: int
    bin_count: int
    bins: tuple[CalibrationBin, ...]
    expected_calibration_error: float
    maximum_calibration_error: float
    brier_score: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "prediction_count": self.prediction_count,
            "bin_count": self.bin_count,
            "bins": [
                {
                    "lower": item.lower,
                    "upper": item.upper,
                    "count": item.count,
                    "mean_probability": item.mean_probability,
                    "observed_rate": item.observed_rate,
                    "absolute_gap": item.absolute_gap,
                }
                for item in self.bins
            ],
            "expected_calibration_error": self.expected_calibration_error,
            "maximum_calibration_error": self.maximum_calibration_error,
            "brier_score": self.brier_score,
            "digest": self.digest,
        }


def analyze_calibration_curve(
    predictions: Sequence[CalibrationPrediction],
    *,
    bins: int = 10,
) -> CalibrationCurveReport:
    if not predictions:
        raise ReverseEngineeringError("calibration curve requires predictions")
    if bins < 2 or bins > 100:
        raise ReverseEngineeringError("bins must be within [2, 100]")
    ids = [item.prediction_id for item in predictions]
    if len(ids) != len(set(ids)):
        raise ReverseEngineeringError("prediction ids must be unique")

    grouped: list[list[CalibrationPrediction]] = [[] for _ in range(bins)]
    for item in predictions:
        index = min(int(item.probability * bins), bins - 1)
        grouped[index].append(item)

    result_bins: list[CalibrationBin] = []
    weighted_gap = 0.0
    maximum_gap = 0.0
    for index, items in enumerate(grouped):
        if not items:
            continue
        mean_probability = sum(item.probability for item in items) / len(items)
        observed_rate = sum(item.outcome for item in items) / len(items)
        gap = abs(mean_probability - observed_rate)
        weighted_gap += gap * len(items)
        maximum_gap = max(maximum_gap, gap)
        result_bins.append(
            CalibrationBin(
                lower=index / bins,
                upper=(index + 1) / bins,
                count=len(items),
                mean_probability=mean_probability,
                observed_rate=observed_rate,
                absolute_gap=gap,
            )
        )
    brier = sum(
        (item.probability - (1.0 if item.outcome else 0.0)) ** 2
        for item in predictions
    ) / len(predictions)
    payload = {
        "bins": bins,
        "predictions": [
            {
                "prediction_id": item.prediction_id,
                "probability": item.probability,
                "outcome": item.outcome,
            }
            for item in sorted(predictions, key=lambda value: value.prediction_id)
        ],
    }
    return CalibrationCurveReport(
        prediction_count=len(predictions),
        bin_count=len(result_bins),
        bins=tuple(result_bins),
        expected_calibration_error=weighted_gap / len(predictions),
        maximum_calibration_error=maximum_gap,
        brier_score=brier,
        digest=stable_digest(payload),
    )
