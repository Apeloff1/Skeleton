"""Fréchet derivative references for the matrix exponential."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix, positive_scalar
from .matrix_algebra2 import frobenius_norm
from .matrix_functions import matrix_exponential


def _aligned_square(
    matrix: Sequence[Sequence[Real]],
    direction: Sequence[Sequence[Real]],
) -> tuple[Matrix, Matrix]:
    source = finite_matrix("matrix", matrix)
    perturbation = finite_matrix("direction", direction)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "Fréchet derivative requires a square source matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    if len(perturbation) != n or len(perturbation[0]) != n:
        raise MathInvariantError(
            "Fréchet direction must match source square shape",
            reason="dimension_mismatch",
            field="direction",
        )
    return source, perturbation


@dataclass(frozen=True, slots=True)
class MatrixFrechetReport:
    exponential: Matrix
    derivative: Matrix
    direction_frobenius: float
    derivative_frobenius: float
    finite_difference_residual_frobenius: float
    finite_difference_step: float
    block_taylor_terms: int
    block_squarings: int


def matrix_exponential_frechet(
    matrix: Sequence[Sequence[Real]],
    direction: Sequence[Sequence[Real]],
    *,
    finite_difference_step: Real = 1e-6,
) -> MatrixFrechetReport:
    source, perturbation = _aligned_square(matrix, direction)
    step = positive_scalar("finite_difference_step", finite_difference_step)
    n = len(source)
    block = tuple(
        tuple(
            source[i][j]
            if i < n and j < n
            else perturbation[i][j - n]
            if i < n and j >= n
            else source[i - n][j - n]
            if i >= n and j >= n
            else 0.0
            for j in range(2 * n)
        )
        for i in range(2 * n)
    )
    block_report = matrix_exponential(block)
    exponential = tuple(
        tuple(block_report.value[i][j] for j in range(n))
        for i in range(n)
    )
    derivative = tuple(
        tuple(block_report.value[i][n + j] for j in range(n))
        for i in range(n)
    )
    plus = tuple(
        tuple(source[i][j] + step * perturbation[i][j] for j in range(n))
        for i in range(n)
    )
    minus = tuple(
        tuple(source[i][j] - step * perturbation[i][j] for j in range(n))
        for i in range(n)
    )
    plus_exp = matrix_exponential(plus).value
    minus_exp = matrix_exponential(minus).value
    finite_difference = tuple(
        tuple((plus_exp[i][j] - minus_exp[i][j]) / (2.0 * step) for j in range(n))
        for i in range(n)
    )
    residual = frobenius_norm(
        tuple(
            tuple(derivative[i][j] - finite_difference[i][j] for j in range(n))
            for i in range(n)
        )
    )
    return MatrixFrechetReport(
        exponential=exponential,
        derivative=derivative,
        direction_frobenius=frobenius_norm(perturbation),
        derivative_frobenius=frobenius_norm(derivative),
        finite_difference_residual_frobenius=residual,
        finite_difference_step=step,
        block_taylor_terms=block_report.taylor_terms,
        block_squarings=block_report.squarings,
    )


def matrix_exponential_relative_condition_proxy(
    matrix: Sequence[Sequence[Real]],
    *,
    finite_difference_step: Real = 1e-6,
) -> float:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "condition proxy requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    source_norm = frobenius_norm(source)
    exponential_norm = frobenius_norm(matrix_exponential(source).value)
    if exponential_norm == 0.0:
        raise MathInvariantError(
            "matrix exponential condition proxy has zero output norm",
            reason="zero_norm",
            field="matrix",
        )
    maximum = 0.0
    for row in range(n):
        for column in range(n):
            basis = tuple(
                tuple(1.0 if i == row and j == column else 0.0 for j in range(n))
                for i in range(n)
            )
            report = matrix_exponential_frechet(
                source,
                basis,
                finite_difference_step=finite_difference_step,
            )
            maximum = max(maximum, report.derivative_frobenius)
    return maximum if source_norm == 0.0 else maximum * source_norm / exponential_norm
