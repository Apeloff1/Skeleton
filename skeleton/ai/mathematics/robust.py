"""Robust descriptive statistics and outlier diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .statistics import median, quantile
from .numerics import compensated_sum


def trimmed_mean(
    values: Sequence[Real] | Iterable[Real],
    *,
    proportion: Real = 0.1,
) -> float:
    observations = sorted(finite_vector("values", values))
    fraction = finite_scalar("proportion", proportion)
    if not 0.0 <= fraction < 0.5:
        raise MathInvariantError(
            "trim proportion must lie in [0, 0.5)",
            reason="invalid_trim_proportion",
            field="proportion",
        )
    trim = int(math.floor(len(observations) * fraction))
    retained = observations[trim:len(observations) - trim if trim else len(observations)]
    if not retained:
        raise MathInvariantError(
            "trim proportion removed all observations",
            reason="insufficient_observations",
            field="proportion",
        )
    return compensated_sum(retained) / len(retained)


def winsorized_mean(
    values: Sequence[Real] | Iterable[Real],
    *,
    proportion: Real = 0.1,
) -> float:
    observations = sorted(finite_vector("values", values))
    fraction = finite_scalar("proportion", proportion)
    if not 0.0 <= fraction < 0.5:
        raise MathInvariantError(
            "winsor proportion must lie in [0, 0.5)",
            reason="invalid_trim_proportion",
            field="proportion",
        )
    trim = int(math.floor(len(observations) * fraction))
    if trim == 0:
        return compensated_sum(observations) / len(observations)
    lower = observations[trim]
    upper = observations[-trim - 1]
    winsorized = tuple(
        lower if value < lower else upper if value > upper else value
        for value in observations
    )
    return compensated_sum(winsorized) / len(winsorized)


def robust_scale_mad(
    values: Sequence[Real] | Iterable[Real],
    *,
    consistency: Real = 1.482602218505602,
) -> float:
    observations = finite_vector("values", values)
    center = median(observations)
    mad = median(tuple(abs(value - center) for value in observations))
    scale = positive_scalar("consistency", consistency)
    return mad * scale


@dataclass(frozen=True, slots=True)
class HuberLocationReport:
    location: float
    scale: float
    iterations: int
    converged: bool
    maximum_weight_change: float


def huber_location(
    values: Sequence[Real] | Iterable[Real],
    *,
    tuning: Real = 1.345,
    tolerance: Real = 1e-10,
    max_iterations: int = 100,
) -> HuberLocationReport:
    observations = finite_vector("values", values)
    c = positive_scalar("tuning", tuning)
    tol = positive_scalar("tolerance", tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    location = median(observations)
    scale = robust_scale_mad(observations)
    if scale == 0.0:
        if all(value == location for value in observations):
            return HuberLocationReport(location, 0.0, 0, True, 0.0)
        # Deterministic fallback for data with MAD=0 but non-identical observations.
        deviations = sorted(abs(value - location) for value in observations if value != location)
        scale = deviations[0] if deviations else 1.0
    previous_weights = tuple(1.0 for _ in observations)
    maximum_change = 0.0

    for iteration in range(1, max_iterations + 1):
        residuals = tuple((value - location) / scale for value in observations)
        weights = tuple(
            1.0 if abs(residual) <= c else c / abs(residual)
            for residual in residuals
        )
        denominator = compensated_sum(weights)
        if denominator <= 0.0:
            raise MathInvariantError(
                "Huber weights lost all mass",
                reason="zero_weight_mass",
                field="weights",
            )
        candidate = compensated_sum(
            weight * value for weight, value in zip(weights, observations)
        ) / denominator
        maximum_change = max(abs(a - b) for a, b in zip(weights, previous_weights))
        if abs(candidate - location) <= tol * max(1.0, abs(location), abs(candidate)):
            return HuberLocationReport(
                location=candidate,
                scale=scale,
                iterations=iteration,
                converged=True,
                maximum_weight_change=maximum_change,
            )
        location = candidate
        previous_weights = weights
    return HuberLocationReport(
        location=location,
        scale=scale,
        iterations=max_iterations,
        converged=False,
        maximum_weight_change=maximum_change,
    )


def modified_z_scores(
    values: Sequence[Real] | Iterable[Real],
    *,
    consistency: Real = 0.6744897501960817,
) -> Vector:
    observations = finite_vector("values", values)
    center = median(observations)
    deviations = tuple(abs(value - center) for value in observations)
    mad = median(deviations)
    coefficient = positive_scalar("consistency", consistency)
    if mad == 0.0:
        if all(value == center for value in observations):
            return tuple(0.0 for _ in observations)
        raise MathInvariantError(
            "modified z-scores are undefined when MAD is zero for non-constant data",
            reason="zero_robust_scale",
            field="values",
        )
    return tuple(coefficient * (value - center) / mad for value in observations)


def robust_interquartile_range(
    values: Sequence[Real] | Iterable[Real],
) -> float:
    observations = finite_vector("values", values)
    return quantile(observations, 0.75) - quantile(observations, 0.25)
