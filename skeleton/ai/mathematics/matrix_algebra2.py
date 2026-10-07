"""Kronecker, matrix-power, norm and stable determinant references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix
from .linear import matmul
from .lu import lu_decompose
from .numerics import compensated_sum


def identity_matrix(size: int) -> Matrix:
    if isinstance(size, bool) or not isinstance(size, int) or size < 1:
        raise MathInvariantError(
            "identity size must be a positive integer",
            reason="invalid_dimension",
            field="size",
        )
    return tuple(
        tuple(1.0 if i == j else 0.0 for j in range(size))
        for i in range(size)
    )


def matrix_trace(matrix: Sequence[Sequence[Real]]) -> float:
    source = finite_matrix("matrix", matrix)
    if len(source) != len(source[0]):
        raise MathInvariantError(
            "trace requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    return compensated_sum(source[i][i] for i in range(len(source)))


def frobenius_norm(matrix: Sequence[Sequence[Real]]) -> float:
    source = finite_matrix("matrix", matrix)
    return math.sqrt(compensated_sum(value * value for row in source for value in row))


def kronecker_product(
    left: Sequence[Sequence[Real]],
    right: Sequence[Sequence[Real]],
) -> Matrix:
    a = finite_matrix("left", left)
    b = finite_matrix("right", right)
    output = []
    for a_row in a:
        for b_row in b:
            row = []
            for a_value in a_row:
                row.extend(a_value * b_value for b_value in b_row)
            output.append(tuple(row))
    return tuple(output)


def matrix_power(
    matrix: Sequence[Sequence[Real]],
    exponent: int,
) -> Matrix:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "matrix power requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 0:
        raise MathInvariantError(
            "matrix exponent must be a non-negative integer",
            reason="invalid_exponent",
            field="exponent",
        )
    result = identity_matrix(n)
    base = source
    power = exponent
    while power:
        if power & 1:
            result = matmul(result, base)
        power >>= 1
        if power:
            base = matmul(base, base)
    return result


@dataclass(frozen=True, slots=True)
class SLogDetReport:
    sign: int
    log_abs_determinant: float
    pivot_condition_proxy: float


def slogdet(
    matrix: Sequence[Sequence[Real]],
    *,
    singular_tolerance: Real = 1e-12,
) -> SLogDetReport:
    report = lu_decompose(matrix, singular_tolerance=singular_tolerance)
    sign = report.parity
    log_abs = 0.0
    for i in range(len(report.upper)):
        pivot = report.upper[i][i]
        if pivot < 0.0:
            sign *= -1
        log_abs += math.log(abs(pivot))
    return SLogDetReport(
        sign=sign,
        log_abs_determinant=log_abs,
        pivot_condition_proxy=report.pivot_condition_proxy,
    )
