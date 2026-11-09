"""Euclidean, angular, simplex, and subspace reference geometry."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import dot, l2_norm, solve_linear_system
from .numerics import compensated_sum


def squared_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "distance vectors must have equal length",
            reason="dimension_mismatch",
            field="distance",
        )
    return compensated_sum((x - y) * (x - y) for x, y in zip(a, b))


def euclidean_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    return math.sqrt(squared_distance(left, right))


def angular_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "angular-distance vectors must have equal length",
            reason="dimension_mismatch",
            field="angular_distance",
        )
    na = l2_norm(a)
    nb = l2_norm(b)
    if na == 0.0 or nb == 0.0:
        raise MathInvariantError(
            "angular distance is undefined for zero vectors",
            reason="zero_norm",
            field="angular_distance",
        )
    cosine = max(-1.0, min(1.0, dot(a, b) / (na * nb)))
    return math.acos(cosine)


def project_probability_simplex(
    values: Sequence[Real],
    *,
    mass: Real = 1.0,
) -> Vector:
    vector = finite_vector("values", values)
    target_mass = positive_scalar("mass", mass)
    ordered = sorted(vector, reverse=True)
    cumulative = 0.0
    rho = -1
    theta = 0.0
    for index, value in enumerate(ordered):
        cumulative += value
        candidate = (cumulative - target_mass) / (index + 1)
        if value - candidate > 0.0:
            rho = index
            theta = candidate
    if rho < 0:
        raise MathInvariantError(
            "simplex projection failed to identify an active set",
            reason="numerical_invariant_failure",
            field="values",
        )
    projected = [max(value - theta, 0.0) for value in vector]
    total = compensated_sum(projected)
    correction = target_mass - total
    if correction:
        pivot = max(range(len(projected)), key=projected.__getitem__)
        projected[pivot] += correction
    if any(value < -1e-14 for value in projected):
        raise MathInvariantError(
            "simplex projection produced negative mass",
            reason="numerical_invariant_failure",
            field="values",
        )
    return tuple(max(0.0, value) for value in projected)


def barycentric_triangle(
    point: Sequence[Real],
    first: Sequence[Real],
    second: Sequence[Real],
    third: Sequence[Real],
    *,
    degeneracy_tolerance: Real = 1e-14,
) -> tuple[float, float, float]:
    p = finite_vector("point", point)
    a = finite_vector("first", first)
    b = finite_vector("second", second)
    c = finite_vector("third", third)
    if not (len(p) == len(a) == len(b) == len(c)):
        raise MathInvariantError(
            "barycentric vectors must have equal dimension",
            reason="dimension_mismatch",
            field="barycentric_triangle",
        )
    tolerance = positive_scalar("degeneracy_tolerance", degeneracy_tolerance)
    v0 = tuple(x - y for x, y in zip(b, a))
    v1 = tuple(x - y for x, y in zip(c, a))
    v2 = tuple(x - y for x, y in zip(p, a))
    d00 = dot(v0, v0)
    d01 = dot(v0, v1)
    d11 = dot(v1, v1)
    d20 = dot(v2, v0)
    d21 = dot(v2, v1)
    denominator = d00 * d11 - d01 * d01
    scale = max(1.0, d00 * d11)
    if abs(denominator) <= tolerance * scale:
        raise MathInvariantError(
            "triangle is degenerate",
            reason="degenerate_geometry",
            field="triangle",
        )
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    u = 1.0 - v - w
    return (
        finite_scalar("barycentric_u", u),
        finite_scalar("barycentric_v", v),
        finite_scalar("barycentric_w", w),
    )


@dataclass(frozen=True, slots=True)
class ProjectionReport:
    coefficients: Vector
    projection: Vector
    residual: Vector
    residual_l2: float


def project_onto_subspace(
    vector: Sequence[Real],
    basis: Sequence[Sequence[Real]],
) -> ProjectionReport:
    target = finite_vector("vector", vector)
    if not basis:
        raise MathInvariantError(
            "subspace basis must not be empty",
            reason="empty_basis",
            field="basis",
        )
    rows = tuple(finite_vector(f"basis[{index}]", row) for index, row in enumerate(basis))
    if any(len(row) != len(target) for row in rows):
        raise MathInvariantError(
            "basis vectors must match target dimension",
            reason="dimension_mismatch",
            field="basis",
        )
    gram = tuple(tuple(dot(left, right) for right in rows) for left in rows)
    rhs = tuple(dot(row, target) for row in rows)
    coefficients = solve_linear_system(gram, rhs).solution
    projection = tuple(
        compensated_sum(coefficient * row[index] for coefficient, row in zip(coefficients, rows))
        for index in range(len(target))
    )
    residual = tuple(value - estimate for value, estimate in zip(target, projection))
    return ProjectionReport(
        coefficients=coefficients,
        projection=projection,
        residual=residual,
        residual_l2=l2_norm(residual),
    )
