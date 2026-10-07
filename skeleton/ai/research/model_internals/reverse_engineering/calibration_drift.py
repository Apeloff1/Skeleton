"""Probe-calibration drift across ordered evaluation windows."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Sequence

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class CalibrationWindow:
    window_id: str
    ordinal: int
    sensitivity: float
    specificity: float
    precision: float | None

    def __post_init__(self) -> None:
        if not self.window_id:
            raise ReverseEngineeringError("calibration window requires identity")
        if self.ordinal < 0:
            raise ReverseEngineeringError("calibration window ordinal must be non-negative")
        for value, name in (
            (self.sensitivity, "sensitivity"),
            (self.specificity, "specificity"),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ReverseEngineeringError(f"{name} must be within [0, 1]")
        if self.precision is not None and (
            not isfinite(self.precision) or not 0.0 <= self.precision <= 1.0
        ):
            raise ReverseEngineeringError("precision must be within [0, 1] when present")


@dataclass(frozen=True)
class CalibrationDriftReport:
    window_count: int
    sensitivity_change: float
    specificity_change: float
    precision_change: float | None
    max_adjacent_balanced_accuracy_change: float
    mean_balanced_accuracy: float
    drift_exceeds_threshold: bool
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_count": self.window_count,
            "sensitivity_change": self.sensitivity_change,
            "specificity_change": self.specificity_change,
            "precision_change": self.precision_change,
            "max_adjacent_balanced_accuracy_change": self.max_adjacent_balanced_accuracy_change,
            "mean_balanced_accuracy": self.mean_balanced_accuracy,
            "drift_exceeds_threshold": self.drift_exceeds_threshold,
            "digest": self.digest,
        }


def analyze_calibration_drift(
    windows: Sequence[CalibrationWindow],
    *,
    threshold: float = 0.1,
) -> CalibrationDriftReport:
    if len(windows) < 2:
        raise ReverseEngineeringError("calibration drift requires at least two windows")
    if not isfinite(threshold) or threshold < 0.0:
        raise ReverseEngineeringError("drift threshold must be finite and non-negative")
    ordered = sorted(windows, key=lambda item: (item.ordinal, item.window_id))
    ordinals = [item.ordinal for item in ordered]
    if len(ordinals) != len(set(ordinals)):
        raise ReverseEngineeringError("calibration window ordinals must be unique")
    balanced = [(item.sensitivity + item.specificity) / 2.0 for item in ordered]
    adjacent = [
        abs(right - left)
        for left, right in zip(balanced, balanced[1:])
    ]
    precisions = [item.precision for item in ordered]
    precision_change = None
    if precisions[0] is not None and precisions[-1] is not None:
        precision_change = precisions[-1] - precisions[0]
    payload = {
        "threshold": threshold,
        "windows": [
            {
                "window_id": item.window_id,
                "ordinal": item.ordinal,
                "sensitivity": item.sensitivity,
                "specificity": item.specificity,
                "precision": item.precision,
            }
            for item in ordered
        ],
    }
    max_change = max(adjacent)
    return CalibrationDriftReport(
        window_count=len(ordered),
        sensitivity_change=ordered[-1].sensitivity - ordered[0].sensitivity,
        specificity_change=ordered[-1].specificity - ordered[0].specificity,
        precision_change=precision_change,
        max_adjacent_balanced_accuracy_change=max_change,
        mean_balanced_accuracy=sum(balanced) / len(balanced),
        drift_exceeds_threshold=max_change > threshold,
        digest=stable_digest(payload),
    )
