"""Calibration metrics for reverse-engineering probes with explicit controls."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class ProbeControlResult:
    result_id: str
    probe_id: str
    expected_positive: bool
    observed_positive: bool
    score: float | None = None

    def __post_init__(self) -> None:
        if not self.result_id or not self.probe_id:
            raise ReverseEngineeringError("probe control result identity is required")
        if self.score is not None and not isfinite(self.score):
            raise ReverseEngineeringError("probe control score must be finite when present")


@dataclass(frozen=True)
class ProbeCalibrationReport:
    probe_id: str
    sample_count: int
    true_positive: int
    true_negative: int
    false_positive: int
    false_negative: int
    sensitivity: float | None
    specificity: float | None
    precision: float | None
    balanced_accuracy: float | None
    positive_rate: float
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "probe_id": self.probe_id,
            "sample_count": self.sample_count,
            "true_positive": self.true_positive,
            "true_negative": self.true_negative,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
            "sensitivity": self.sensitivity,
            "specificity": self.specificity,
            "precision": self.precision,
            "balanced_accuracy": self.balanced_accuracy,
            "positive_rate": self.positive_rate,
            "digest": self.digest,
        }


def calibrate_probes(
    results: Sequence[ProbeControlResult],
) -> tuple[ProbeCalibrationReport, ...]:
    if not results:
        raise ReverseEngineeringError("probe calibration requires control results")
    grouped: dict[str, list[ProbeControlResult]] = {}
    seen_ids: set[str] = set()
    for result in results:
        if result.result_id in seen_ids:
            raise ReverseEngineeringError(f"duplicate result_id: {result.result_id!r}")
        seen_ids.add(result.result_id)
        grouped.setdefault(result.probe_id, []).append(result)

    reports: list[ProbeCalibrationReport] = []
    for probe_id, items in sorted(grouped.items()):
        ordered = sorted(items, key=lambda item: item.result_id)
        tp = sum(item.expected_positive and item.observed_positive for item in ordered)
        tn = sum((not item.expected_positive) and (not item.observed_positive) for item in ordered)
        fp = sum((not item.expected_positive) and item.observed_positive for item in ordered)
        fn = sum(item.expected_positive and (not item.observed_positive) for item in ordered)
        positive_total = tp + fn
        negative_total = tn + fp
        observed_positive = tp + fp
        sensitivity = tp / positive_total if positive_total else None
        specificity = tn / negative_total if negative_total else None
        precision = tp / observed_positive if observed_positive else None
        balanced = (
            (sensitivity + specificity) / 2.0
            if sensitivity is not None and specificity is not None
            else None
        )
        payload = {
            "probe_id": probe_id,
            "results": [
                {
                    "result_id": item.result_id,
                    "expected_positive": item.expected_positive,
                    "observed_positive": item.observed_positive,
                    "score": item.score,
                }
                for item in ordered
            ],
        }
        reports.append(
            ProbeCalibrationReport(
                probe_id=probe_id,
                sample_count=len(ordered),
                true_positive=tp,
                true_negative=tn,
                false_positive=fp,
                false_negative=fn,
                sensitivity=sensitivity,
                specificity=specificity,
                precision=precision,
                balanced_accuracy=balanced,
                positive_rate=observed_positive / len(ordered),
                digest=stable_digest(payload),
            )
        )
    return tuple(reports)
