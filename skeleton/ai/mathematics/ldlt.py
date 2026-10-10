"""Symmetric LDL^T factorization and solve references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class LDLTReport:
    lower: Matrix
    diagonal: Vector
    reconstruction_linf: float
    minimum_abs_pivot: float
    positive_pivots: int
    negative_pivots: int


def ldlt_decompose(
    matrix: Sequence[Sequence[Real]],
    *,
    symmetry_tolerance: Real = 1e-12,
    pivot_tolerance: Real = 1e-14,
) -> LDLTReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "LDL^T decomposition requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    sym_tol = positive_scalar("symmetry_tolerance", symmetry_tolerance)
    pivot_tol = positive_scalar("pivot_tolerance", pivot_tolerance)
    scale = max(1.0, max(abs(value) for row in source for value in row))
    for i in range(n):
        for j in range(i + 1, n):
            if abs(source[i][j] - source[j][i]) > sym_tol * scale:
                raise MathInvariantError(
                    "LDL^T decomposition requires a symmetric matrix",
                    reason="non_symmetric_matrix",
                    field="matrix",
                )

    lower = [[0.0] * n for _ in range(n)]
    diagonal = [0.0] * n
    for i in range(n):
        lower[i][i] = 1.0
        pivot = source[i][i] - compensated_sum(
            lower[i][k] * lower[i][k] * diagonal[k]
            for k in range(i)
        )
        if abs(pivot) <= pivot_tol * scale:
            raise MathInvariantError(
                "unpivoted LDL^T encountered a zero or tiny pivot",
                reason="singular_or_pivot_required",
                field=f"matrix[{i}][{i}]",
            )
        diagonal[i] = pivot
        for row in range(i + 1, n):
            numerator = source[row][i] - compensated_sum(
                lower[row][k] * lower[i][k] * diagonal[k]
                for k in range(i)
            )
            lower[row][i] = numerator / pivot
            if not math.isfinite(lower[row][i]):
                raise MathInvariantError(
                    "LDL^T factor produced a non-finite value",
                    reason="non_finite_result",
                    field="lower",
                )

    factor = tuple(tuple(row) for row in lower)
    diagonal_vector = tuple(diagonal)
    residual = 0.0
    for i in range(n):
        for j in range(n):
            estimate = compensated_sum(
                factor[i][k] * diagonal_vector[k] * factor[j][k]
                for k in range(n)
            )
            residual = max(residual, abs(estimate - source[i][j]))
    minimum = min(abs(value) for value in diagonal_vector)
    return LDLTReport(
        lower=factor,
        diagonal=diagonal_vector,
        reconstruction_linf=residual,
        minimum_abs_pivot=minimum,
        positive_pivots=sum(value > 0.0 for value in diagonal_vector),
        negative_pivots=sum(value < 0.0 for value in diagonal_vector),
    )


def ldlt_solve(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    symmetry_tolerance: Real = 1e-12,
    pivot_tolerance: Real = 1e-14,
) -> Vector:
    report = ldlt_decompose(
        matrix,
        symmetry_tolerance=symmetry_tolerance,
        pivot_tolerance=pivot_tolerance,
    )
    target = finite_vector("rhs", rhs)
    n = len(report.diagonal)
    if len(target) != n:
        raise MathInvariantError(
            "LDL^T rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    y = [0.0] * n
    for i in range(n):
        y[i] = target[i] - compensated_sum(
            report.lower[i][j] * y[j] for j in range(i)
        )
    z = [y[i] / report.diagonal[i] for i in range(n)]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = z[i] - compensated_sum(
            report.lower[j][i] * x[j]
            for j in range(i + 1, n)
        )
    return finite_vector("solution", x)
