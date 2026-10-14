"""Truncated-SVD low-rank approximation references with energy evidence."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_scalar
from .numerics import compensated_sum
from .svd import singular_value_decomposition


@dataclass(frozen=True, slots=True)
class LowRankApproximationReport:
    approximation: Matrix
    requested_rank: int
    effective_rank: int
    singular_values: Vector
    retained_energy_fraction: float
    residual_frobenius: float
    relative_residual_frobenius: float


def truncated_svd_approximation(
    matrix: Sequence[Sequence[Real]],
    rank: int,
) -> LowRankApproximationReport:
    source = finite_matrix("matrix", matrix)
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise MathInvariantError(
            "low-rank approximation rank must be a positive integer",
            reason="invalid_rank",
            field="rank",
        )
    svd = singular_value_decomposition(source)
    if rank > svd.rank:
        raise MathInvariantError(
            "requested rank exceeds numerical matrix rank",
            reason="invalid_rank",
            field="rank",
        )
    rows = len(source)
    columns = len(source[0])
    approximation = tuple(
        tuple(
            compensated_sum(
                svd.singular_values[k]
                * svd.left_vectors[k][i]
                * svd.right_vectors[k][j]
                for k in range(rank)
            )
            for j in range(columns)
        )
        for i in range(rows)
    )
    residual_squared = compensated_sum(
        (source[i][j] - approximation[i][j]) ** 2
        for i in range(rows)
        for j in range(columns)
    )
    source_squared = compensated_sum(
        value * value for row in source for value in row
    )
    total_energy = compensated_sum(value * value for value in svd.singular_values)
    retained_energy = compensated_sum(
        svd.singular_values[k] ** 2 for k in range(rank)
    )
    return LowRankApproximationReport(
        approximation=approximation,
        requested_rank=rank,
        effective_rank=svd.rank,
        singular_values=svd.singular_values,
        retained_energy_fraction=retained_energy / total_energy if total_energy else 1.0,
        residual_frobenius=math.sqrt(max(0.0, residual_squared)),
        relative_residual_frobenius=(
            0.0 if source_squared == 0.0 else math.sqrt(residual_squared / source_squared)
        ),
    )


def rank_for_retained_energy(
    matrix: Sequence[Sequence[Real]],
    fraction: Real,
) -> int:
    source = finite_matrix("matrix", matrix)
    target = finite_scalar("fraction", fraction)
    if not 0.0 < target <= 1.0:
        raise MathInvariantError(
            "retained-energy fraction must lie in (0, 1]",
            reason="invalid_probability",
            field="fraction",
        )
    svd = singular_value_decomposition(source)
    total = compensated_sum(value * value for value in svd.singular_values)
    if total == 0.0:
        raise MathInvariantError(
            "zero matrix has no positive retained-energy rank",
            reason="zero_norm",
            field="matrix",
        )
    cumulative = 0.0
    for index, singular in enumerate(svd.singular_values, start=1):
        cumulative += singular * singular
        if cumulative / total >= target:
            return index
    return svd.rank
