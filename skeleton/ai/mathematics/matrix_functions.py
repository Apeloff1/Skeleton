"""Reference matrix exponential via scaling, Taylor summation, and squaring."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix, positive_scalar
from .linear import matmul
from .matrix_algebra2 import frobenius_norm, identity_matrix


def _scale_matrix(matrix: Matrix, factor: float) -> Matrix:
    return tuple(tuple(value * factor for value in row) for row in matrix)


def _add_matrix(left: Matrix, right: Matrix) -> Matrix:
    return tuple(
        tuple(a + b for a, b in zip(left_row, right_row))
        for left_row, right_row in zip(left, right)
    )


@dataclass(frozen=True, slots=True)
class MatrixExponentialReport:
    value: Matrix
    taylor_terms: int
    squarings: int
    final_term_frobenius: float
    converged: bool


def matrix_exponential(
    matrix: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-15,
    max_terms: int = 128,
) -> MatrixExponentialReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "matrix exponential requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    tol = positive_scalar("tolerance", tolerance)
    if isinstance(max_terms, bool) or not isinstance(max_terms, int) or max_terms < 2:
        raise MathInvariantError(
            "max_terms must be an integer >= 2",
            reason="invalid_iteration_limit",
            field="max_terms",
        )
    one_norm = max(
        sum(abs(source[row][column]) for row in range(n))
        for column in range(n)
    )
    squarings = 0 if one_norm <= 0.5 else max(0, math.ceil(math.log2(one_norm / 0.5)))
    scale = 2.0 ** squarings
    reduced = _scale_matrix(source, 1.0 / scale)

    result = identity_matrix(n)
    term = identity_matrix(n)
    final_norm = frobenius_norm(term)
    converged = False
    used_terms = 0
    for order in range(1, max_terms + 1):
        term = _scale_matrix(matmul(term, reduced), 1.0 / order)
        result = _add_matrix(result, term)
        final_norm = frobenius_norm(term)
        used_terms = order
        if final_norm <= tol * max(1.0, frobenius_norm(result)):
            converged = True
            break
    if not converged:
        raise MathInvariantError(
            "matrix exponential Taylor series did not converge",
            reason="matrix_function_non_convergence",
            field="matrix",
        )
    for _ in range(squarings):
        result = matmul(result, result)
    return MatrixExponentialReport(
        value=result,
        taylor_terms=used_terms,
        squarings=squarings,
        final_term_frobenius=final_norm,
        converged=True,
    )
