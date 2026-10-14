"""Distribution and covariance geometry reference metrics."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_matrix, finite_vector
from .decompositions import solve_cholesky
from .numerics import compensated_sum
from .probability import normalize_distribution


def _probability_pair(
    left: Sequence[Real],
    right: Sequence[Real],
) -> tuple[Vector, Vector]:
    p = normalize_distribution(left)
    q = normalize_distribution(right)
    if len(p) != len(q):
        raise MathInvariantError(
            "probability vectors must have equal dimension",
            reason="dimension_mismatch",
            field="distribution",
        )
    return p, q


def total_variation_distance(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    p, q = _probability_pair(left, right)
    return 0.5 * compensated_sum(abs(a - b) for a, b in zip(p, q))


def hellinger_distance(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    p, q = _probability_pair(left, right)
    squared = 0.5 * compensated_sum(
        (math.sqrt(a) - math.sqrt(b)) ** 2
        for a, b in zip(p, q)
    )
    return math.sqrt(max(0.0, squared))


def bhattacharyya_coefficient(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    p, q = _probability_pair(left, right)
    value = compensated_sum(math.sqrt(a * b) for a, b in zip(p, q))
    return max(0.0, min(1.0, value))


def bhattacharyya_distance(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    coefficient = bhattacharyya_coefficient(left, right)
    if coefficient == 0.0:
        raise MathInvariantError(
            "Bhattacharyya distance is infinite for disjoint support",
            reason="infinite_divergence",
            field="distribution",
        )
    return -math.log(coefficient)


def fisher_rao_distance(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    coefficient = bhattacharyya_coefficient(left, right)
    return 2.0 * math.acos(max(-1.0, min(1.0, coefficient)))


def mahalanobis_distance(
    left: Sequence[Real],
    right: Sequence[Real],
    covariance: Sequence[Sequence[Real]],
) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "Mahalanobis vectors must have equal dimension",
            reason="dimension_mismatch",
            field="mahalanobis",
        )
    matrix = finite_matrix("covariance", covariance)
    if len(matrix) != len(a) or len(matrix[0]) != len(a):
        raise MathInvariantError(
            "covariance dimension must match vectors",
            reason="dimension_mismatch",
            field="covariance",
        )
    delta = tuple(x - y for x, y in zip(a, b))
    precision_times_delta = solve_cholesky(matrix, delta)
    squared = compensated_sum(
        value * transformed
        for value, transformed in zip(delta, precision_times_delta)
    )
    if squared < 0.0 and abs(squared) <= 1e-12:
        squared = 0.0
    if squared < 0.0:
        raise MathInvariantError(
            "Mahalanobis quadratic form became negative",
            reason="numerical_invariant_failure",
            field="covariance",
        )
    return math.sqrt(squared)
