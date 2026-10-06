"""Symmetric rank-one and Cholesky update/downdate reference primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_scalar, finite_vector
from .decompositions import cholesky_decompose
from .numerics import compensated_sum


def symmetric_rank_one_update(
    matrix: Sequence[Sequence[Real]],
    vector: Sequence[Real],
    *,
    alpha: Real = 1.0,
) -> Matrix:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "symmetric rank-one update requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    values = finite_vector("vector", vector)
    if len(values) != n:
        raise MathInvariantError(
            "rank-one vector dimension mismatch",
            reason="dimension_mismatch",
            field="vector",
        )
    coefficient = finite_scalar("alpha", alpha)
    for i in range(n):
        for j in range(i + 1, n):
            if source[i][j] != source[j][i]:
                raise MathInvariantError(
                    "rank-one symmetric update requires an exactly symmetric matrix",
                    reason="non_symmetric_matrix",
                    field="matrix",
                )
    return tuple(
        tuple(source[i][j] + coefficient * values[i] * values[j] for j in range(n))
        for i in range(n)
    )


@dataclass(frozen=True, slots=True)
class CholeskyUpdateReport:
    lower: Matrix
    sign: int
    reconstruction_linf: float
    minimum_diagonal: float


def cholesky_rank_one_update(
    lower: Sequence[Sequence[Real]],
    vector: Sequence[Real],
    *,
    sign: int = 1,
) -> CholeskyUpdateReport:
    factor = finite_matrix("lower", lower)
    n = len(factor)
    if len(factor[0]) != n:
        raise MathInvariantError(
            "Cholesky update requires a square lower factor",
            reason="non_square_matrix",
            field="lower",
        )
    if sign not in {-1, 1} or isinstance(sign, bool):
        raise MathInvariantError(
            "Cholesky rank-one sign must be +1 or -1",
            reason="invalid_update_sign",
            field="sign",
        )
    for i in range(n):
        if factor[i][i] <= 0.0:
            raise MathInvariantError(
                "Cholesky factor diagonal must be positive",
                reason="non_positive_diagonal",
                field=f"lower[{i}][{i}]",
            )
        for j in range(i + 1, n):
            if factor[i][j] != 0.0:
                raise MathInvariantError(
                    "Cholesky update expects a lower-triangular factor",
                    reason="non_triangular_matrix",
                    field="lower",
                )
    work = [list(row) for row in factor]
    update = list(finite_vector("vector", vector))
    if len(update) != n:
        raise MathInvariantError(
            "Cholesky update vector dimension mismatch",
            reason="dimension_mismatch",
            field="vector",
        )

    for k in range(n):
        diagonal = work[k][k]
        radicand = diagonal * diagonal + sign * update[k] * update[k]
        if radicand <= 0.0:
            raise MathInvariantError(
                "Cholesky downdate would destroy positive definiteness",
                reason="non_positive_definite_update",
                field=f"vector[{k}]",
            )
        radius = math.sqrt(radicand)
        c = radius / diagonal
        s = update[k] / diagonal
        work[k][k] = radius
        for row in range(k + 1, n):
            updated_entry = (work[row][k] + sign * s * update[row]) / c
            update[row] = c * update[row] - s * updated_entry
            work[row][k] = updated_entry

    result = tuple(tuple(row) for row in work)
    original_matrix = tuple(
        tuple(
            compensated_sum(factor[i][k] * factor[j][k] for k in range(min(i, j) + 1))
            for j in range(n)
        )
        for i in range(n)
    )
    target = symmetric_rank_one_update(original_matrix, vector, alpha=float(sign))
    reconstructed = tuple(
        tuple(
            compensated_sum(result[i][k] * result[j][k] for k in range(min(i, j) + 1))
            for j in range(n)
        )
        for i in range(n)
    )
    residual = max(
        abs(reconstructed[i][j] - target[i][j])
        for i in range(n)
        for j in range(n)
    )
    return CholeskyUpdateReport(
        lower=result,
        sign=sign,
        reconstruction_linf=residual,
        minimum_diagonal=min(result[i][i] for i in range(n)),
    )


def cholesky_factor_after_rank_one_update(
    matrix: Sequence[Sequence[Real]],
    vector: Sequence[Real],
    *,
    sign: int = 1,
) -> CholeskyUpdateReport:
    base = cholesky_decompose(matrix)
    return cholesky_rank_one_update(base.lower, vector, sign=sign)
