"""General metric and set-distance reference primitives."""
from __future__ import annotations

import math
from numbers import Real
from typing import Hashable, Iterable, Sequence, TypeVar

from .contracts import MathInvariantError, Matrix, Vector, finite_vector, positive_scalar
from .linear import cosine_similarity
from .numerics import compensated_sum


T = TypeVar("T", bound=Hashable)


def _pair(left: Sequence[Real], right: Sequence[Real]) -> tuple[Vector, Vector]:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "distance vectors must have equal dimension",
            reason="dimension_mismatch",
            field="distance",
        )
    return a, b


def minkowski_distance(
    left: Sequence[Real],
    right: Sequence[Real],
    *,
    order: Real = 2.0,
) -> float:
    a, b = _pair(left, right)
    p = positive_scalar("order", order)
    if p < 1.0:
        raise MathInvariantError(
            "Minkowski order must be >= 1",
            reason="invalid_metric_order",
            field="order",
        )
    return compensated_sum(abs(x - y) ** p for x, y in zip(a, b)) ** (1.0 / p)


def manhattan_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    return minkowski_distance(left, right, order=1.0)


def chebyshev_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    a, b = _pair(left, right)
    return max(abs(x - y) for x, y in zip(a, b))


def canberra_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    a, b = _pair(left, right)
    terms = []
    for x, y in zip(a, b):
        denominator = abs(x) + abs(y)
        terms.append(0.0 if denominator == 0.0 else abs(x - y) / denominator)
    return compensated_sum(terms)


def bray_curtis_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    a, b = _pair(left, right)
    denominator = compensated_sum(abs(x) + abs(y) for x, y in zip(a, b))
    if denominator == 0.0:
        return 0.0
    return compensated_sum(abs(x - y) for x, y in zip(a, b)) / denominator


def cosine_distance(left: Sequence[Real], right: Sequence[Real]) -> float:
    return 1.0 - cosine_similarity(left, right)


def jaccard_distance(left: Iterable[T], right: Iterable[T]) -> float:
    a = set(left)
    b = set(right)
    union = a | b
    if not union:
        return 0.0
    return 1.0 - len(a & b) / len(union)


def dice_distance(left: Iterable[T], right: Iterable[T]) -> float:
    a = set(left)
    b = set(right)
    denominator = len(a) + len(b)
    if denominator == 0:
        return 0.0
    return 1.0 - 2.0 * len(a & b) / denominator


def weighted_jaccard_distance(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    a, b = _pair(left, right)
    if any(value < 0.0 for value in a + b):
        raise MathInvariantError(
            "weighted Jaccard inputs must be non-negative",
            reason="negative_weight",
            field="distance",
        )
    denominator = compensated_sum(max(x, y) for x, y in zip(a, b))
    if denominator == 0.0:
        return 0.0
    similarity = compensated_sum(min(x, y) for x, y in zip(a, b)) / denominator
    return 1.0 - similarity


def pairwise_distance_matrix(
    rows: Sequence[Sequence[Real]],
    *,
    order: Real = 2.0,
) -> Matrix:
    vectors = tuple(finite_vector(f"rows[{index}]", row) for index, row in enumerate(rows))
    if not vectors:
        raise MathInvariantError(
            "pairwise distance matrix requires vectors",
            reason="empty_matrix",
            field="rows",
        )
    width = len(vectors[0])
    if any(len(row) != width for row in vectors):
        raise MathInvariantError(
            "pairwise vectors must have consistent dimension",
            reason="ragged_matrix",
            field="rows",
        )
    return tuple(
        tuple(minkowski_distance(left, right, order=order) for right in vectors)
        for left in vectors
    )
