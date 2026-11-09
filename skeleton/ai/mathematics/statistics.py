"""Stable descriptive statistics and covariance reference primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_vector, positive_scalar
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class MomentReport:
    count: int
    mean: float
    population_variance: float
    sample_variance: float | None
    standard_deviation: float
    minimum: float
    maximum: float


def moments(values: Sequence[Real] | Iterable[Real]) -> MomentReport:
    observations = finite_vector("values", values)
    count = 0
    mean = 0.0
    m2 = 0.0
    minimum = math.inf
    maximum = -math.inf
    for value in observations:
        count += 1
        delta = value - mean
        mean += delta / count
        delta2 = value - mean
        m2 += delta * delta2
        minimum = min(minimum, value)
        maximum = max(maximum, value)
    population = max(0.0, m2 / count)
    sample = None if count < 2 else max(0.0, m2 / (count - 1))
    return MomentReport(
        count=count,
        mean=mean,
        population_variance=population,
        sample_variance=sample,
        standard_deviation=math.sqrt(population),
        minimum=minimum,
        maximum=maximum,
    )


def covariance(
    left: Sequence[Real] | Iterable[Real],
    right: Sequence[Real] | Iterable[Real],
    *,
    sample: bool = False,
) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "covariance vectors must have equal length",
            reason="dimension_mismatch",
            field="covariance",
        )
    if sample and len(a) < 2:
        raise MathInvariantError(
            "sample covariance requires at least two observations",
            reason="insufficient_observations",
            field="covariance",
        )
    mean_a = moments(a).mean
    mean_b = moments(b).mean
    numerator = compensated_sum(
        (x - mean_a) * (y - mean_b)
        for x, y in zip(a, b)
    )
    denominator = len(a) - 1 if sample else len(a)
    return numerator / denominator


def correlation(
    left: Sequence[Real] | Iterable[Real],
    right: Sequence[Real] | Iterable[Real],
) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "correlation vectors must have equal length",
            reason="dimension_mismatch",
            field="correlation",
        )
    var_a = moments(a).population_variance
    var_b = moments(b).population_variance
    if var_a == 0.0 or var_b == 0.0:
        raise MathInvariantError(
            "correlation is undefined for zero-variance input",
            reason="zero_variance",
            field="correlation",
        )
    result = covariance(a, b) / math.sqrt(var_a * var_b)
    return max(-1.0, min(1.0, result))


def covariance_matrix(
    rows: Sequence[Sequence[Real]],
    *,
    sample: bool = False,
) -> Matrix:
    if not rows:
        raise MathInvariantError(
            "covariance matrix requires observations",
            reason="empty_matrix",
            field="rows",
        )
    matrix = tuple(finite_vector(f"rows[{index}]", row) for index, row in enumerate(rows))
    width = len(matrix[0])
    if any(len(row) != width for row in matrix):
        raise MathInvariantError(
            "covariance observations must be rectangular",
            reason="ragged_matrix",
            field="rows",
        )
    if sample and len(matrix) < 2:
        raise MathInvariantError(
            "sample covariance matrix requires at least two observations",
            reason="insufficient_observations",
            field="rows",
        )
    columns = tuple(tuple(row[column] for row in matrix) for column in range(width))
    return tuple(
        tuple(covariance(left, right, sample=sample) for right in columns)
        for left in columns
    )


def quantile(values: Sequence[Real] | Iterable[Real], probability: Real) -> float:
    observations = sorted(finite_vector("values", values))
    p = positive_scalar("probability", probability) if probability != 0 else 0.0
    if not 0.0 <= p <= 1.0:
        raise MathInvariantError(
            "quantile probability must lie in [0, 1]",
            reason="invalid_probability",
            field="probability",
        )
    if len(observations) == 1:
        return observations[0]
    position = p * (len(observations) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return observations[lower]
    fraction = position - lower
    return observations[lower] * (1.0 - fraction) + observations[upper] * fraction


def median(values: Sequence[Real] | Iterable[Real]) -> float:
    return quantile(values, 0.5)


def median_absolute_deviation(
    values: Sequence[Real] | Iterable[Real],
    *,
    scale: Real = 1.0,
) -> float:
    observations = finite_vector("values", values)
    center = median(observations)
    raw = median(tuple(abs(value - center) for value in observations))
    return raw * positive_scalar("scale", scale)


def standardize(values: Sequence[Real] | Iterable[Real]) -> Vector:
    observations = finite_vector("values", values)
    report = moments(observations)
    if report.standard_deviation == 0.0:
        raise MathInvariantError(
            "standardization requires non-zero variance",
            reason="zero_variance",
            field="values",
        )
    return tuple(
        (value - report.mean) / report.standard_deviation
        for value in observations
    )
