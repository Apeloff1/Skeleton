"""Weighted isotonic regression via deterministic pool-adjacent violators."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector, positive_scalar
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class IsotonicBlock:
    start: int
    end: int
    weight: float
    value: float


@dataclass(frozen=True, slots=True)
class IsotonicReport:
    fitted: Vector
    blocks: tuple[IsotonicBlock, ...]
    weighted_squared_error: float
    increasing: bool


def isotonic_regression(
    values: Sequence[Real],
    *,
    weights: Sequence[Real] | None = None,
    increasing: bool = True,
) -> IsotonicReport:
    observations = finite_vector("values", values)
    if weights is None:
        clean_weights = tuple(1.0 for _ in observations)
    else:
        clean_weights = finite_vector("weights", weights)
        if len(clean_weights) != len(observations):
            raise MathInvariantError(
                "isotonic weights must match observation count",
                reason="dimension_mismatch",
                field="weights",
            )
        clean_weights = tuple(
            positive_scalar(f"weights[{index}]", value)
            for index, value in enumerate(clean_weights)
        )
    sign = 1.0 if increasing else -1.0
    transformed = tuple(sign * value for value in observations)

    blocks: list[list[float | int]] = []
    for index, (value, weight) in enumerate(zip(transformed, clean_weights)):
        blocks.append([index, index, weight, weight * value])
        while len(blocks) >= 2:
            left = blocks[-2]
            right = blocks[-1]
            left_mean = float(left[3]) / float(left[2])
            right_mean = float(right[3]) / float(right[2])
            if left_mean < right_mean:
                break
            merged = [
                int(left[0]),
                int(right[1]),
                float(left[2]) + float(right[2]),
                float(left[3]) + float(right[3]),
            ]
            blocks[-2:] = [merged]

    fitted = [0.0] * len(observations)
    reports: list[IsotonicBlock] = []
    for start_raw, end_raw, weight_raw, sum_raw in blocks:
        start = int(start_raw)
        end = int(end_raw)
        weight = float(weight_raw)
        value = sign * (float(sum_raw) / weight)
        for index in range(start, end + 1):
            fitted[index] = value
        reports.append(IsotonicBlock(start, end, weight, value))

    error = compensated_sum(
        weight * (observed - estimate) ** 2
        for observed, estimate, weight in zip(observations, fitted, clean_weights)
    )
    return IsotonicReport(
        fitted=tuple(fitted),
        blocks=tuple(reports),
        weighted_squared_error=error,
        increasing=increasing,
    )
