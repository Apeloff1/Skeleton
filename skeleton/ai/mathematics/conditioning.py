"""Matrix norm, conditioning and backward-error reference diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, finite_matrix, finite_vector
from .linear import matvec
from .lu import matrix_inverse


def matrix_one_norm(matrix: Sequence[Sequence[Real]]) -> float:
    source = finite_matrix("matrix", matrix)
    return max(
        sum(abs(source[row][column]) for row in range(len(source)))
        for column in range(len(source[0]))
    )


def matrix_infinity_norm(matrix: Sequence[Sequence[Real]]) -> float:
    source = finite_matrix("matrix", matrix)
    return max(sum(abs(value) for value in row) for row in source)


def matrix_max_norm(matrix: Sequence[Sequence[Real]]) -> float:
    source = finite_matrix("matrix", matrix)
    return max(abs(value) for row in source for value in row)


@dataclass(frozen=True, slots=True)
class ConditionReport:
    norm: str
    matrix_norm: float
    inverse_norm: float
    condition_number: float
    inverse_residual_linf: float


def condition_number(
    matrix: Sequence[Sequence[Real]],
    *,
    norm: str = "1",
    singular_tolerance: Real = 1e-12,
) -> ConditionReport:
    source = finite_matrix("matrix", matrix)
    if len(source) != len(source[0]):
        raise MathInvariantError(
            "condition number requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    if norm not in {"1", "inf"}:
        raise MathInvariantError(
            "condition norm must be '1' or 'inf'",
            reason="invalid_norm",
            field="norm",
        )
    inverse = matrix_inverse(source, singular_tolerance=singular_tolerance)
    norm_function = matrix_one_norm if norm == "1" else matrix_infinity_norm
    matrix_norm_value = norm_function(source)
    inverse_norm_value = norm_function(inverse.inverse)
    return ConditionReport(
        norm=norm,
        matrix_norm=matrix_norm_value,
        inverse_norm=inverse_norm_value,
        condition_number=matrix_norm_value * inverse_norm_value,
        inverse_residual_linf=inverse.residual_linf,
    )


@dataclass(frozen=True, slots=True)
class BackwardErrorReport:
    residual_linf: float
    relative_backward_error: float
    matrix_infinity_norm: float
    solution_infinity_norm: float
    rhs_infinity_norm: float


def linear_backward_error(
    matrix: Sequence[Sequence[Real]],
    solution: Sequence[Real],
    rhs: Sequence[Real],
) -> BackwardErrorReport:
    source = finite_matrix("matrix", matrix)
    x = finite_vector("solution", solution)
    b = finite_vector("rhs", rhs)
    if len(source[0]) != len(x) or len(source) != len(b):
        raise MathInvariantError(
            "backward-error dimensions must match A x = b",
            reason="dimension_mismatch",
            field="linear_system",
        )
    image = matvec(source, x)
    residual = max(abs(target - value) for target, value in zip(b, image))
    matrix_norm = matrix_infinity_norm(source)
    solution_norm = max(abs(value) for value in x)
    rhs_norm = max(abs(value) for value in b)
    denominator = matrix_norm * solution_norm + rhs_norm
    relative = 0.0 if denominator == 0.0 and residual == 0.0 else residual / denominator
    if not math.isfinite(relative):
        raise MathInvariantError(
            "relative backward error became non-finite",
            reason="non_finite_result",
            field="linear_system",
        )
    return BackwardErrorReport(
        residual_linf=residual,
        relative_backward_error=relative,
        matrix_infinity_norm=matrix_norm,
        solution_infinity_norm=solution_norm,
        rhs_infinity_norm=rhs_norm,
    )
