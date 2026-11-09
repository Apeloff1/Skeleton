"""Pivoted LU factorization, determinant, inverse and solve references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .linear import matmul, matvec
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class LUReport:
    lower: Matrix
    upper: Matrix
    permutation: tuple[int, ...]
    parity: int
    reconstruction_linf: float
    minimum_pivot: float
    maximum_pivot: float
    pivot_condition_proxy: float


def lu_decompose(
    matrix: Sequence[Sequence[Real]],
    *,
    singular_tolerance: Real = 1e-12,
) -> LUReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "LU decomposition requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    tolerance = positive_scalar("singular_tolerance", singular_tolerance)
    upper = [list(row) for row in source]
    lower = [[0.0] * n for _ in range(n)]
    permutation = list(range(n))
    parity = 1
    pivots: list[float] = []
    scale = max(1.0, max(abs(value) for row in source for value in row))

    for column in range(n):
        pivot_row = max(range(column, n), key=lambda row: abs(upper[row][column]))
        pivot = upper[pivot_row][column]
        if abs(pivot) <= tolerance * scale:
            raise MathInvariantError(
                "matrix is singular or numerically rank deficient",
                reason="singular_matrix",
                field="matrix",
            )
        if pivot_row != column:
            upper[column], upper[pivot_row] = upper[pivot_row], upper[column]
            permutation[column], permutation[pivot_row] = permutation[pivot_row], permutation[column]
            for prior in range(column):
                lower[column][prior], lower[pivot_row][prior] = (
                    lower[pivot_row][prior],
                    lower[column][prior],
                )
            parity *= -1
        pivot = upper[column][column]
        pivots.append(abs(pivot))
        lower[column][column] = 1.0
        for row in range(column + 1, n):
            factor = upper[row][column] / pivot
            lower[row][column] = factor
            upper[row][column] = 0.0
            for index in range(column + 1, n):
                upper[row][index] -= factor * upper[column][index]
                if not math.isfinite(upper[row][index]):
                    raise MathInvariantError(
                        "LU elimination produced a non-finite value",
                        reason="non_finite_result",
                        field="matrix",
                    )

    lower_matrix = tuple(tuple(row) for row in lower)
    upper_matrix = tuple(tuple(row) for row in upper)
    reconstructed = matmul(lower_matrix, upper_matrix)
    permuted_source = tuple(source[index] for index in permutation)
    residual = max(
        abs(reconstructed[i][j] - permuted_source[i][j])
        for i in range(n)
        for j in range(n)
    )
    minimum = min(pivots)
    maximum = max(pivots)
    return LUReport(
        lower=lower_matrix,
        upper=upper_matrix,
        permutation=tuple(permutation),
        parity=parity,
        reconstruction_linf=residual,
        minimum_pivot=minimum,
        maximum_pivot=maximum,
        pivot_condition_proxy=maximum / minimum,
    )


def lu_solve(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    singular_tolerance: Real = 1e-12,
) -> Vector:
    report = lu_decompose(matrix, singular_tolerance=singular_tolerance)
    target = finite_vector("rhs", rhs)
    n = len(report.lower)
    if len(target) != n:
        raise MathInvariantError(
            "rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    permuted = tuple(target[index] for index in report.permutation)
    y = [0.0] * n
    for row in range(n):
        correction = compensated_sum(report.lower[row][j] * y[j] for j in range(row))
        y[row] = permuted[row] - correction

    x = [0.0] * n
    for row in range(n - 1, -1, -1):
        correction = compensated_sum(
            report.upper[row][j] * x[j]
            for j in range(row + 1, n)
        )
        pivot = report.upper[row][row]
        x[row] = (y[row] - correction) / pivot
        if not math.isfinite(x[row]):
            raise MathInvariantError(
                "LU solve produced a non-finite result",
                reason="non_finite_result",
                field="solution",
            )
    return tuple(x)


def determinant(
    matrix: Sequence[Sequence[Real]],
    *,
    singular_tolerance: Real = 1e-12,
) -> float:
    report = lu_decompose(matrix, singular_tolerance=singular_tolerance)
    value = float(report.parity)
    for index in range(len(report.upper)):
        value *= report.upper[index][index]
    if not math.isfinite(value):
        raise MathInvariantError(
            "determinant is non-finite",
            reason="non_finite_result",
            field="determinant",
        )
    return value


@dataclass(frozen=True, slots=True)
class InverseReport:
    inverse: Matrix
    residual_linf: float


def matrix_inverse(
    matrix: Sequence[Sequence[Real]],
    *,
    singular_tolerance: Real = 1e-12,
) -> InverseReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "matrix inverse requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    columns = []
    for column in range(n):
        rhs = tuple(1.0 if row == column else 0.0 for row in range(n))
        columns.append(lu_solve(source, rhs, singular_tolerance=singular_tolerance))
    inverse = tuple(
        tuple(columns[column][row] for column in range(n))
        for row in range(n)
    )
    product = matmul(source, inverse)
    residual = max(
        abs(product[i][j] - (1.0 if i == j else 0.0))
        for i in range(n)
        for j in range(n)
    )
    return InverseReport(inverse=inverse, residual_linf=residual)
