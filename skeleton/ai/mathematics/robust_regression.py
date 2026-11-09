"""Deterministic robust linear-regression reference estimators."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_vector, positive_scalar
from .decompositions import least_squares
from .numerics import compensated_sum
from .statistics import median


def _design(
    rows: Sequence[Sequence[Real]],
    targets: Sequence[Real],
    *,
    intercept: bool,
) -> tuple[Matrix, Vector]:
    if not rows:
        raise MathInvariantError(
            "robust regression requires observations",
            reason="empty_matrix",
            field="rows",
        )
    features = tuple(finite_vector(f"rows[{index}]", row) for index, row in enumerate(rows))
    width = len(features[0])
    if any(len(row) != width for row in features):
        raise MathInvariantError(
            "robust regression rows must be rectangular",
            reason="ragged_matrix",
            field="rows",
        )
    y = finite_vector("targets", targets)
    if len(y) != len(features):
        raise MathInvariantError(
            "robust regression targets must match row count",
            reason="dimension_mismatch",
            field="targets",
        )
    matrix = tuple(((1.0,) + row) if intercept else row for row in features)
    return matrix, y


def _predict(design: Matrix, coefficients: Vector) -> Vector:
    return tuple(
        compensated_sum(coefficient * value for coefficient, value in zip(coefficients, row))
        for row in design
    )


def _mad_scale(residuals: Vector) -> float:
    center = median(residuals)
    mad = median(tuple(abs(value - center) for value in residuals))
    scale = 1.482602218505602 * mad
    if scale > 0.0:
        return scale
    nonzero = sorted(abs(value) for value in residuals if value != 0.0)
    return nonzero[0] if nonzero else 0.0


@dataclass(frozen=True, slots=True)
class HuberRegressionReport:
    coefficients: Vector
    residuals: Vector
    weights: Vector
    scale: float
    iterations: int
    converged: bool
    weighted_residual_l2: float


def huber_regression(
    rows: Sequence[Sequence[Real]],
    targets: Sequence[Real],
    *,
    intercept: bool = True,
    tuning: Real = 1.345,
    tolerance: Real = 1e-10,
    max_iterations: int = 100,
) -> HuberRegressionReport:
    design, y = _design(rows, targets, intercept=intercept)
    c = positive_scalar("tuning", tuning)
    tol = positive_scalar("tolerance", tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    coefficients = least_squares(design, y).solution
    weights = tuple(1.0 for _ in y)
    scale = 0.0
    for iteration in range(1, max_iterations + 1):
        predictions = _predict(design, coefficients)
        residuals = tuple(target - prediction for target, prediction in zip(y, predictions))
        scale = _mad_scale(residuals)
        if scale == 0.0:
            return HuberRegressionReport(
                coefficients,
                residuals,
                weights,
                0.0,
                iteration - 1,
                True,
                0.0,
            )

        weights = tuple(
            1.0 if abs(residual) <= c * scale else (c * scale) / abs(residual)
            for residual in residuals
        )
        weighted_design = tuple(
            tuple(math.sqrt(weight) * value for value in row)
            for weight, row in zip(weights, design)
        )
        weighted_targets = tuple(math.sqrt(weight) * target for weight, target in zip(weights, y))
        candidate = least_squares(weighted_design, weighted_targets).solution
        delta = math.sqrt(compensated_sum((a - b) ** 2 for a, b in zip(candidate, coefficients)))
        coefficient_scale = max(
            1.0,
            math.sqrt(compensated_sum(value * value for value in coefficients)),
            math.sqrt(compensated_sum(value * value for value in candidate)),
        )
        coefficients = candidate
        if delta <= tol * coefficient_scale:
            predictions = _predict(design, coefficients)
            residuals = tuple(target - prediction for target, prediction in zip(y, predictions))
            weighted_l2 = math.sqrt(
                compensated_sum(weight * residual * residual for weight, residual in zip(weights, residuals))
            )
            return HuberRegressionReport(
                coefficients,
                residuals,
                weights,
                scale,
                iteration,
                True,
                weighted_l2,
            )

    predictions = _predict(design, coefficients)
    residuals = tuple(target - prediction for target, prediction in zip(y, predictions))
    weighted_l2 = math.sqrt(
        compensated_sum(weight * residual * residual for weight, residual in zip(weights, residuals))
    )
    return HuberRegressionReport(
        coefficients,
        residuals,
        weights,
        scale,
        max_iterations,
        False,
        weighted_l2,
    )


@dataclass(frozen=True, slots=True)
class TheilSenReport:
    intercept: float
    slope: float
    pairwise_slopes: Vector
    residual_median_absolute: float


def theil_sen_regression(
    x: Sequence[Real],
    y: Sequence[Real],
) -> TheilSenReport:
    xs = finite_vector("x", x)
    ys = finite_vector("y", y)
    if len(xs) != len(ys) or len(xs) < 2:
        raise MathInvariantError(
            "Theil-Sen inputs must have equal length >= 2",
            reason="dimension_mismatch",
            field="samples",
        )
    slopes = []
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            delta_x = xs[j] - xs[i]
            if delta_x != 0.0:
                slopes.append((ys[j] - ys[i]) / delta_x)
    if not slopes:
        raise MathInvariantError(
            "Theil-Sen requires at least two distinct x values",
            reason="zero_variance",
            field="x",
        )
    slope = median(slopes)
    intercept = median(tuple(target - slope * value for value, target in zip(xs, ys)))
    residuals = tuple(target - (intercept + slope * value) for value, target in zip(xs, ys))
    return TheilSenReport(
        intercept=intercept,
        slope=slope,
        pairwise_slopes=tuple(slopes),
        residual_median_absolute=median(tuple(abs(value) for value in residuals)),
    )
