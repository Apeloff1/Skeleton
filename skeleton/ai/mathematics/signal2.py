"""Windowing, cross-correlation and rolling signal diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector
from .decompositions import least_squares
from .numerics import compensated_sum


def _count(count: int) -> int:
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise MathInvariantError(
            "window length must be a positive integer",
            reason="invalid_window_length",
            field="count",
        )
    return count


def hann_window(count: int) -> Vector:
    n = _count(count)
    if n == 1:
        return (1.0,)
    return tuple(0.5 - 0.5 * math.cos(2.0 * math.pi * index / (n - 1)) for index in range(n))


def hamming_window(count: int) -> Vector:
    n = _count(count)
    if n == 1:
        return (1.0,)
    return tuple(0.54 - 0.46 * math.cos(2.0 * math.pi * index / (n - 1)) for index in range(n))


def blackman_window(count: int) -> Vector:
    n = _count(count)
    if n == 1:
        return (1.0,)
    return tuple(
        0.42
        - 0.5 * math.cos(2.0 * math.pi * index / (n - 1))
        + 0.08 * math.cos(4.0 * math.pi * index / (n - 1))
        for index in range(n)
    )


@dataclass(frozen=True, slots=True)
class CrossCorrelationReport:
    lags: tuple[int, ...]
    values: Vector
    maximum_lag: int
    maximum_value: float


def cross_correlation(
    left: Sequence[Real],
    right: Sequence[Real],
    *,
    normalized: bool = False,
) -> CrossCorrelationReport:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    lags = tuple(range(-(len(b) - 1), len(a)))
    values = []
    left_energy = compensated_sum(value * value for value in a)
    right_energy = compensated_sum(value * value for value in b)
    normalization = math.sqrt(left_energy * right_energy)
    if normalized and normalization == 0.0:
        raise MathInvariantError(
            "normalized cross-correlation requires non-zero energy",
            reason="zero_variance",
            field="signals",
        )

    for lag in lags:
        total = 0.0
        for i in range(len(a)):
            j = i - lag
            if 0 <= j < len(b):
                total += a[i] * b[j]
        values.append(total / normalization if normalized else total)

    maximum_index = max(range(len(values)), key=lambda index: (values[index], -abs(lags[index]), -lags[index]))
    return CrossCorrelationReport(
        lags=lags,
        values=tuple(values),
        maximum_lag=lags[maximum_index],
        maximum_value=values[maximum_index],
    )


def moving_average(values: Sequence[Real], width: int) -> Vector:
    observations = finite_vector("values", values)
    window = _count(width)
    if window > len(observations):
        raise MathInvariantError(
            "moving-average width exceeds observation count",
            reason="invalid_window_length",
            field="width",
        )
    running = compensated_sum(observations[:window])
    output = [running / window]
    for index in range(window, len(observations)):
        running += observations[index] - observations[index - window]
        output.append(running / window)
    return tuple(output)


def moving_rms(values: Sequence[Real], width: int) -> Vector:
    observations = finite_vector("values", values)
    window = _count(width)
    if window > len(observations):
        raise MathInvariantError(
            "moving-RMS width exceeds observation count",
            reason="invalid_window_length",
            field="width",
        )
    squares = tuple(value * value for value in observations)
    return tuple(math.sqrt(value) for value in moving_average(squares, window))


def linear_detrend(values: Sequence[Real]) -> Vector:
    observations = finite_vector("values", values)
    if len(observations) < 2:
        return (0.0,)
    design = tuple((1.0, float(index)) for index in range(len(observations)))
    fit = least_squares(design, observations)
    intercept, slope = fit.solution
    return tuple(
        value - (intercept + slope * index)
        for index, value in enumerate(observations)
    )
