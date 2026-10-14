"""Deterministic interpolation and polynomial approximation references."""
from __future__ import annotations

import bisect
import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector
from .numerics import compensated_sum


def _samples(
    nodes: Sequence[Real],
    values: Sequence[Real],
) -> tuple[Vector, Vector]:
    x = finite_vector("nodes", nodes)
    y = finite_vector("values", values)
    if len(x) != len(y):
        raise MathInvariantError(
            "nodes and values must have equal length",
            reason="dimension_mismatch",
            field="samples",
        )
    for index in range(1, len(x)):
        if x[index] <= x[index - 1]:
            raise MathInvariantError(
                "interpolation nodes must be strictly increasing",
                reason="non_monotonic_nodes",
                field=f"nodes[{index}]",
            )
    return x, y


def horner(coefficients: Sequence[Real], x: Real) -> float:
    coeffs = finite_vector("coefficients", coefficients)
    point = finite_scalar("x", x)
    result = 0.0
    for coefficient in reversed(coeffs):
        result = result * point + coefficient
        finite_scalar("polynomial_value", result)
    return result


def chebyshev_nodes(
    count: int,
    *,
    lower: Real = -1.0,
    upper: Real = 1.0,
) -> Vector:
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise MathInvariantError(
            "Chebyshev node count must be a positive integer",
            reason="invalid_node_count",
            field="count",
        )
    a = finite_scalar("lower", lower)
    b = finite_scalar("upper", upper)
    if b <= a:
        raise MathInvariantError(
            "Chebyshev interval must satisfy lower < upper",
            reason="invalid_interval",
            field="interval",
        )
    midpoint = (a + b) * 0.5
    radius = (b - a) * 0.5
    nodes = [
        midpoint + radius * math.cos((2 * index + 1) * math.pi / (2 * count))
        for index in range(count)
    ]
    return tuple(sorted(nodes))


def barycentric_weights(nodes: Sequence[Real]) -> Vector:
    x = finite_vector("nodes", nodes)
    weights: list[float] = []
    for i, xi in enumerate(x):
        factors = []
        for j, xj in enumerate(x):
            if i == j:
                continue
            difference = xi - xj
            if difference == 0.0:
                raise MathInvariantError(
                    "barycentric nodes must be distinct",
                    reason="duplicate_node",
                    field="nodes",
                )
            factors.append(difference)
        denominator = 1.0
        for factor in factors:
            denominator *= factor
            finite_scalar("barycentric_denominator", denominator)
        weights.append(finite_scalar("barycentric_weight", 1.0 / denominator))
    return tuple(weights)


def barycentric_interpolate(
    nodes: Sequence[Real],
    values: Sequence[Real],
    x: Real,
    *,
    weights: Sequence[Real] | None = None,
) -> float:
    x_nodes = finite_vector("nodes", nodes)
    y_values = finite_vector("values", values)
    if len(x_nodes) != len(y_values):
        raise MathInvariantError(
            "nodes and values must have equal length",
            reason="dimension_mismatch",
            field="samples",
        )
    point = finite_scalar("x", x)
    if weights is None:
        w = barycentric_weights(x_nodes)
    else:
        w = finite_vector("weights", weights)
        if len(w) != len(x_nodes):
            raise MathInvariantError(
                "barycentric weights must match node count",
                reason="dimension_mismatch",
                field="weights",
            )
    for node, value in zip(x_nodes, y_values):
        if point == node:
            return value
    numerator_terms = []
    denominator_terms = []
    for node, value, weight in zip(x_nodes, y_values, w):
        ratio = weight / (point - node)
        numerator_terms.append(ratio * value)
        denominator_terms.append(ratio)
    denominator = compensated_sum(denominator_terms)
    if denominator == 0.0:
        raise MathInvariantError(
            "barycentric denominator vanished",
            reason="numerical_invariant_failure",
            field="x",
        )
    return finite_scalar(
        "interpolated_value",
        compensated_sum(numerator_terms) / denominator,
    )


def piecewise_linear_interpolate(
    nodes: Sequence[Real],
    values: Sequence[Real],
    x: Real,
    *,
    extrapolation: str = "error",
) -> float:
    x_nodes, y_values = _samples(nodes, values)
    point = finite_scalar("x", x)
    if extrapolation not in {"error", "clamp", "linear"}:
        raise MathInvariantError(
            "extrapolation must be error, clamp, or linear",
            reason="invalid_extrapolation_policy",
            field="extrapolation",
        )
    if len(x_nodes) == 1:
        if point != x_nodes[0] and extrapolation == "error":
            raise MathInvariantError(
                "point lies outside interpolation domain",
                reason="extrapolation_forbidden",
                field="x",
            )
        return y_values[0]

    if point < x_nodes[0]:
        if extrapolation == "error":
            raise MathInvariantError(
                "point lies below interpolation domain",
                reason="extrapolation_forbidden",
                field="x",
            )
        if extrapolation == "clamp":
            return y_values[0]
        left = 0
    elif point > x_nodes[-1]:
        if extrapolation == "error":
            raise MathInvariantError(
                "point lies above interpolation domain",
                reason="extrapolation_forbidden",
                field="x",
            )
        if extrapolation == "clamp":
            return y_values[-1]
        left = len(x_nodes) - 2
    else:
        insertion = bisect.bisect_right(x_nodes, point)
        if insertion and x_nodes[insertion - 1] == point:
            return y_values[insertion - 1]
        left = max(0, min(len(x_nodes) - 2, insertion - 1))

    x0, x1 = x_nodes[left], x_nodes[left + 1]
    y0, y1 = y_values[left], y_values[left + 1]
    fraction = (point - x0) / (x1 - x0)
    return finite_scalar("interpolated_value", y0 + fraction * (y1 - y0))


def newton_divided_differences(
    nodes: Sequence[Real],
    values: Sequence[Real],
) -> Vector:
    x = finite_vector("nodes", nodes)
    coefficients = list(finite_vector("values", values))
    if len(x) != len(coefficients):
        raise MathInvariantError(
            "nodes and values must have equal length",
            reason="dimension_mismatch",
            field="samples",
        )
    if len(set(x)) != len(x):
        raise MathInvariantError(
            "Newton interpolation nodes must be distinct",
            reason="duplicate_node",
            field="nodes",
        )
    n = len(x)
    for order in range(1, n):
        for index in range(n - 1, order - 1, -1):
            denominator = x[index] - x[index - order]
            coefficients[index] = finite_scalar(
                "divided_difference",
                (coefficients[index] - coefficients[index - 1]) / denominator,
            )
    return tuple(coefficients)


def newton_interpolate(
    nodes: Sequence[Real],
    coefficients: Sequence[Real],
    x: Real,
) -> float:
    x_nodes = finite_vector("nodes", nodes)
    coeffs = finite_vector("coefficients", coefficients)
    if len(x_nodes) != len(coeffs):
        raise MathInvariantError(
            "nodes and Newton coefficients must have equal length",
            reason="dimension_mismatch",
            field="coefficients",
        )
    point = finite_scalar("x", x)
    result = coeffs[-1]
    for index in range(len(coeffs) - 2, -1, -1):
        result = coeffs[index] + (point - x_nodes[index]) * result
        finite_scalar("interpolated_value", result)
    return result
