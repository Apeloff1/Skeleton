"""Deterministic dense linear algebra reference implementation."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Iterable, Sequence

from .contracts import (
    MathInvariantError,
    Matrix,
    Vector,
    finite_matrix,
    finite_scalar,
    finite_vector,
    positive_scalar,
    same_length,
)
from .numerics import compensated_sum


def dot(left: Sequence[Real] | Iterable[Real], right: Sequence[Real] | Iterable[Real]) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    same_length("dot", a, b)
    return compensated_sum(x * y for x, y in zip(a, b))


def l2_norm(values: Sequence[Real] | Iterable[Real]) -> float:
    vector = finite_vector("values", values)
    return math.hypot(*vector)


def cosine_similarity(
    left: Sequence[Real] | Iterable[Real],
    right: Sequence[Real] | Iterable[Real],
) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    same_length("cosine_similarity", a, b)
    na = math.hypot(*a)
    nb = math.hypot(*b)
    if na == 0.0 or nb == 0.0:
        raise MathInvariantError(
            "cosine similarity is undefined for a zero vector",
            reason="zero_norm",
            field="vector",
        )
    value = dot(a, b) / (na * nb)
    return max(-1.0, min(1.0, value))


def transpose(matrix: Sequence[Sequence[Real]]) -> Matrix:
    source = finite_matrix("matrix", matrix)
    return tuple(tuple(source[row][column] for row in range(len(source))) for column in range(len(source[0])))


def matvec(matrix: Sequence[Sequence[Real]], vector: Sequence[Real]) -> Vector:
    source = finite_matrix("matrix", matrix)
    values = finite_vector("vector", vector)
    if len(source[0]) != len(values):
        raise MathInvariantError(
            "matrix/vector dimension mismatch",
            reason="dimension_mismatch",
            field="matvec",
        )
    return tuple(dot(row, values) for row in source)


def matmul(left: Sequence[Sequence[Real]], right: Sequence[Sequence[Real]]) -> Matrix:
    a = finite_matrix("left", left)
    b = finite_matrix("right", right)
    if len(a[0]) != len(b):
        raise MathInvariantError(
            "matrix multiplication dimension mismatch",
            reason="dimension_mismatch",
            field="matmul",
        )
    columns = transpose(b)
    return tuple(tuple(dot(row, column) for column in columns) for row in a)


@dataclass(frozen=True, slots=True)
class LinearSolveReport:
    solution: Vector
    residual_linf: float
    minimum_pivot: float
    maximum_pivot: float
    pivot_condition_proxy: float


def solve_linear_system(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    singular_tolerance: Real = 1e-12,
) -> LinearSolveReport:
    """Solve Ax=b with scaled partial pivoting and explicit residual evidence."""

    source = finite_matrix("matrix", matrix)
    target = finite_vector("rhs", rhs)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "linear solve requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    if len(target) != n:
        raise MathInvariantError(
            "rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    tolerance = positive_scalar("singular_tolerance", singular_tolerance)
    work = [list(row) + [target[index]] for index, row in enumerate(source)]
    row_scales = [max(abs(value) for value in row) for row in source]
    if any(scale == 0.0 for scale in row_scales):
        raise MathInvariantError(
            "linear system contains an all-zero row",
            reason="singular_matrix",
            field="matrix",
        )

    pivots: list[float] = []
    for column in range(n):
        pivot_row = max(
            range(column, n),
            key=lambda row: abs(work[row][column]) / row_scales[row],
        )
        pivot = work[pivot_row][column]
        cutoff = tolerance * max(1.0, row_scales[pivot_row])
        if abs(pivot) <= cutoff:
            raise MathInvariantError(
                "matrix is singular or numerically rank-deficient",
                reason="singular_matrix",
                field="matrix",
            )
        if pivot_row != column:
            work[column], work[pivot_row] = work[pivot_row], work[column]
            row_scales[column], row_scales[pivot_row] = row_scales[pivot_row], row_scales[column]
        pivot = work[column][column]
        pivots.append(abs(pivot))
        for row in range(column + 1, n):
            factor = work[row][column] / pivot
            work[row][column] = 0.0
            for index in range(column + 1, n + 1):
                work[row][index] -= factor * work[column][index]

    solution = [0.0] * n
    for row in range(n - 1, -1, -1):
        remainder = compensated_sum(work[row][column] * solution[column] for column in range(row + 1, n))
        pivot = work[row][row]
        value = (work[row][n] - remainder) / pivot
        if not math.isfinite(value):
            raise MathInvariantError(
                "linear solve produced a non-finite value",
                reason="non_finite_result",
                field="solution",
            )
        solution[row] = value

    result = tuple(solution)
    predicted = matvec(source, result)
    residual = max(abs(got - expected) for got, expected in zip(predicted, target))
    minimum = min(pivots)
    maximum = max(pivots)
    proxy = maximum / minimum
    return LinearSolveReport(
        solution=result,
        residual_linf=residual,
        minimum_pivot=minimum,
        maximum_pivot=maximum,
        pivot_condition_proxy=proxy,
    )
