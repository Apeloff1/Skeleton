"""Pure calibration metrics with no ledger, correction, or routing authority."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, finite_scalar, finite_vector
from .losses import brier_score
from .numerics import compensated_sum
from .probability import normalize_distribution


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float
    empirical_rate: float
    absolute_gap: float


@dataclass(frozen=True, slots=True)
class CalibrationMetricReport:
    bins: tuple[CalibrationBin, ...]
    expected_calibration_error: float
    maximum_calibration_error: float
    brier_score: float
    sample_count: int


def _bin_count(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise MathInvariantError(
            "calibration bin count must be an integer >= 2",
            reason="invalid_bin_count",
            field="bins",
        )
    return value


def binary_calibration_report(
    confidences: Sequence[Real],
    outcomes: Sequence[bool | int],
    *,
    bins: int = 10,
) -> CalibrationMetricReport:
    probabilities = finite_vector("confidences", confidences)
    if len(probabilities) != len(outcomes):
        raise MathInvariantError(
            "confidence and outcome arrays must have equal length",
            reason="dimension_mismatch",
            field="calibration",
        )
    bucket_count = _bin_count(bins)
    labels: list[int] = []
    for index, (confidence, outcome) in enumerate(zip(probabilities, outcomes)):
        if not 0.0 <= confidence <= 1.0:
            raise MathInvariantError(
                "confidence must lie in [0, 1]",
                reason="invalid_probability",
                field=f"confidences[{index}]",
            )
        if isinstance(outcome, bool):
            labels.append(int(outcome))
        elif isinstance(outcome, int) and outcome in {0, 1}:
            labels.append(outcome)
        else:
            raise MathInvariantError(
                "binary outcomes must be booleans or 0/1 integers",
                reason="invalid_outcome",
                field=f"outcomes[{index}]",
            )

    bucket_confidence: list[list[float]] = [[] for _ in range(bucket_count)]
    bucket_labels: list[list[int]] = [[] for _ in range(bucket_count)]
    for confidence, label in zip(probabilities, labels):
        index = min(bucket_count - 1, int(confidence * bucket_count))
        bucket_confidence[index].append(confidence)
        bucket_labels[index].append(label)

    summaries: list[CalibrationBin] = []
    weighted_gaps = []
    for index in range(bucket_count):
        if not bucket_confidence[index]:
            continue
        count = len(bucket_confidence[index])
        mean_confidence = compensated_sum(bucket_confidence[index]) / count
        empirical_rate = sum(bucket_labels[index]) / count
        gap = abs(mean_confidence - empirical_rate)
        summaries.append(
            CalibrationBin(
                lower=index / bucket_count,
                upper=(index + 1) / bucket_count,
                count=count,
                mean_confidence=mean_confidence,
                empirical_rate=empirical_rate,
                absolute_gap=gap,
            )
        )
        weighted_gaps.append(gap * count)

    sample_count = len(probabilities)
    ece = compensated_sum(weighted_gaps) / sample_count
    mce = max((item.absolute_gap for item in summaries), default=0.0)
    brier = compensated_sum(
        (confidence - label) ** 2
        for confidence, label in zip(probabilities, labels)
    ) / sample_count
    return CalibrationMetricReport(
        bins=tuple(summaries),
        expected_calibration_error=ece,
        maximum_calibration_error=mce,
        brier_score=brier,
        sample_count=sample_count,
    )


def top_label_calibration_report(
    probability_rows: Sequence[Sequence[Real]],
    target_indices: Sequence[int],
    *,
    bins: int = 10,
) -> CalibrationMetricReport:
    if not probability_rows:
        raise MathInvariantError(
            "probability rows must not be empty",
            reason="empty_matrix",
            field="probability_rows",
        )
    if len(probability_rows) != len(target_indices):
        raise MathInvariantError(
            "probability rows and targets must have equal length",
            reason="dimension_mismatch",
            field="targets",
        )
    confidences: list[float] = []
    correctness: list[int] = []
    brier_values: list[float] = []
    width: int | None = None
    for row_index, (row, target) in enumerate(zip(probability_rows, target_indices)):
        probabilities = normalize_distribution(row)
        if width is None:
            width = len(probabilities)
        elif len(probabilities) != width:
            raise MathInvariantError(
                "probability rows must have consistent width",
                reason="ragged_matrix",
                field=f"probability_rows[{row_index}]",
            )
        if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < len(probabilities):
            raise MathInvariantError(
                "target index is out of range",
                reason="invalid_target_index",
                field=f"target_indices[{row_index}]",
            )
        predicted = max(range(len(probabilities)), key=lambda index: (probabilities[index], -index))
        confidences.append(probabilities[predicted])
        correctness.append(int(predicted == target))
        brier_values.append(brier_score(probabilities, target))

    report = binary_calibration_report(confidences, correctness, bins=bins)
    return CalibrationMetricReport(
        bins=report.bins,
        expected_calibration_error=report.expected_calibration_error,
        maximum_calibration_error=report.maximum_calibration_error,
        brier_score=compensated_sum(brier_values) / len(brier_values),
        sample_count=report.sample_count,
    )
