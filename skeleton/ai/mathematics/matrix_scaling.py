"""Deterministic row/column matrix equilibration references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, positive_scalar


def apply_diagonal_scaling(
    matrix: Sequence[Sequence[Real]],
    left_scale: Sequence[Real],
    right_scale: Sequence[Real],
) -> Matrix:
    source = finite_matrix("matrix", matrix)
    left = tuple(float(value) for value in left_scale)
    right = tuple(float(value) for value in right_scale)
    if len(left) != len(source) or len(right) != len(source[0]):
        raise MathInvariantError(
            "diagonal scaling dimensions must match matrix",
            reason="dimension_mismatch",
            field="scales",
        )
    if any(not math.isfinite(value) or value <= 0.0 for value in left + right):
        raise MathInvariantError(
            "matrix scaling factors must be finite and positive",
            reason="invalid_scale",
            field="scales",
        )
    return tuple(
        tuple(left[i] * source[i][j] * right[j] for j in range(len(right)))
        for i in range(len(left))
    )


@dataclass(frozen=True, slots=True)
class EquilibrationReport:
    scaled_matrix: Matrix
    left_scale: Vector
    right_scale: Vector
    iterations: int
    converged: bool
    maximum_row_norm_error: float
    maximum_column_norm_error: float
    original_dynamic_range: float
    scaled_dynamic_range: float


def _dynamic_range(matrix: Matrix) -> float:
    nonzero = [abs(value) for row in matrix for value in row if value != 0.0]
    if not nonzero:
        return 1.0
    return max(nonzero) / min(nonzero)


def equilibrate_matrix(
    matrix: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-8,
    max_iterations: int = 200,
) -> EquilibrationReport:
    source = finite_matrix("matrix", matrix)
    tol = positive_scalar("tolerance", tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    rows = len(source)
    columns = len(source[0])
    if any(all(value == 0.0 for value in row) for row in source):
        raise MathInvariantError(
            "matrix equilibration requires non-zero support in every row",
            reason="zero_support",
            field="matrix",
        )
    for column in range(columns):
        if all(source[row][column] == 0.0 for row in range(rows)):
            raise MathInvariantError(
                "matrix equilibration requires non-zero support in every column",
                reason="zero_support",
                field="matrix",
            )

    scaled = [list(row) for row in source]
    left = [1.0] * rows
    right = [1.0] * columns
    converged = False
    row_error = math.inf
    column_error = math.inf
    iterations = 0

    for iterations in range(1, max_iterations + 1):
        row_norms = [max(abs(value) for value in row) for row in scaled]
        for i, norm in enumerate(row_norms):
            factor = 1.0 / math.sqrt(norm)
            left[i] *= factor
            scaled[i] = [value * factor for value in scaled[i]]

        column_norms = [
            max(abs(scaled[row][column]) for row in range(rows))
            for column in range(columns)
        ]
        for j, norm in enumerate(column_norms):
            factor = 1.0 / math.sqrt(norm)
            right[j] *= factor
            for i in range(rows):
                scaled[i][j] *= factor

        row_norms = [max(abs(value) for value in row) for row in scaled]
        column_norms = [
            max(abs(scaled[row][column]) for row in range(rows))
            for column in range(columns)
        ]
        row_error = max(abs(norm - 1.0) for norm in row_norms)
        column_error = max(abs(norm - 1.0) for norm in column_norms)
        if max(row_error, column_error) <= tol:
            converged = True
            break

    scaled_matrix = tuple(tuple(row) for row in scaled)
    return EquilibrationReport(
        scaled_matrix=scaled_matrix,
        left_scale=tuple(left),
        right_scale=tuple(right),
        iterations=iterations,
        converged=converged,
        maximum_row_norm_error=row_error,
        maximum_column_norm_error=column_error,
        original_dynamic_range=_dynamic_range(source),
        scaled_dynamic_range=_dynamic_range(scaled_matrix),
    )
