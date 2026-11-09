"""Empirical CDF, histogram and one-dimensional Gaussian KDE references."""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .numerics import compensated_sum
from .probability import normalize_distribution
from .statistics import quantile


@dataclass(frozen=True, slots=True)
class EmpiricalCDF:
    sorted_values: Vector

    def evaluate(self, x: Real) -> float:
        point = finite_scalar("x", x)
        return bisect.bisect_right(self.sorted_values, point) / len(self.sorted_values)

    def quantile(self, probability: Real) -> float:
        return quantile(self.sorted_values, probability)


def empirical_cdf(values: Sequence[Real]) -> EmpiricalCDF:
    observations = tuple(sorted(finite_vector("values", values)))
    return EmpiricalCDF(observations)


@dataclass(frozen=True, slots=True)
class HistogramReport:
    edges: Vector
    counts: tuple[int, ...]
    probabilities: Vector
    densities: Vector
    sample_count: int


def histogram(
    values: Sequence[Real],
    *,
    bins: int = 10,
    lower: Real | None = None,
    upper: Real | None = None,
) -> HistogramReport:
    observations = finite_vector("values", values)
    if isinstance(bins, bool) or not isinstance(bins, int) or bins < 1:
        raise MathInvariantError(
            "histogram bins must be a positive integer",
            reason="invalid_bin_count",
            field="bins",
        )
    lo = min(observations) if lower is None else finite_scalar("lower", lower)
    hi = max(observations) if upper is None else finite_scalar("upper", upper)
    if hi <= lo:
        # A constant sample receives a deterministic unit-width support interval.
        if lower is None and upper is None and hi == lo:
            lo -= 0.5
            hi += 0.5
        else:
            raise MathInvariantError(
                "histogram interval must satisfy lower < upper",
                reason="invalid_interval",
                field="bounds",
            )
    if any(value < lo or value > hi for value in observations):
        raise MathInvariantError(
            "histogram bounds do not contain every observation",
            reason="sample_out_of_bounds",
            field="bounds",
        )
    width = (hi - lo) / bins
    counts = [0] * bins
    for value in observations:
        index = bins - 1 if value == hi else int((value - lo) / width)
        index = max(0, min(bins - 1, index))
        counts[index] += 1
    probabilities = tuple(count / len(observations) for count in counts)
    densities = tuple(probability / width for probability in probabilities)
    edges = tuple(lo + width * index for index in range(bins + 1))
    return HistogramReport(
        edges=edges,
        counts=tuple(counts),
        probabilities=probabilities,
        densities=densities,
        sample_count=len(observations),
    )


def silverman_bandwidth(values: Sequence[Real]) -> float:
    observations = finite_vector("values", values)
    n = len(observations)
    if n < 2:
        raise MathInvariantError(
            "bandwidth estimation requires at least two observations",
            reason="insufficient_observations",
            field="values",
        )
    mean = compensated_sum(observations) / n
    variance = compensated_sum((value - mean) ** 2 for value in observations) / (n - 1)
    standard_deviation = math.sqrt(max(0.0, variance))
    iqr = quantile(observations, 0.75) - quantile(observations, 0.25)
    robust_scale = iqr / 1.349 if iqr > 0.0 else standard_deviation
    scale = min(standard_deviation, robust_scale) if standard_deviation > 0.0 and robust_scale > 0.0 else max(standard_deviation, robust_scale)
    if scale <= 0.0:
        raise MathInvariantError(
            "Silverman bandwidth is undefined for a constant sample",
            reason="zero_variance",
            field="values",
        )
    return 0.9 * scale * n ** (-0.2)


def gaussian_kde_density(
    samples: Sequence[Real],
    points: Sequence[Real],
    *,
    bandwidth: Real | None = None,
    weights: Sequence[Real] | None = None,
) -> Vector:
    observations = finite_vector("samples", samples)
    queries = finite_vector("points", points)
    h = silverman_bandwidth(observations) if bandwidth is None else positive_scalar("bandwidth", bandwidth)
    probabilities = (
        tuple(1.0 / len(observations) for _ in observations)
        if weights is None
        else normalize_distribution(weights)
    )
    if len(probabilities) != len(observations):
        raise MathInvariantError(
            "KDE weights must match sample count",
            reason="dimension_mismatch",
            field="weights",
        )
    normalization = 1.0 / (math.sqrt(2.0 * math.pi) * h)
    output = []
    for point in queries:
        density = compensated_sum(
            weight * math.exp(-0.5 * ((point - sample) / h) ** 2)
            for sample, weight in zip(observations, probabilities)
        ) * normalization
        output.append(finite_scalar("kde_density", density))
    return tuple(output)
