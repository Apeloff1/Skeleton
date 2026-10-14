"""Thin singular-value decomposition and pseudoinverse references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .eigensystems import symmetric_eigensystem
from .linear import matvec, transpose
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class SVDReport:
    singular_values: Vector
    left_vectors: Matrix
    right_vectors: Matrix
    rank: int
    reconstruction_linf: float
    condition_number: float | None


def singular_value_decomposition(
    matrix: Sequence[Sequence[Real]],
    *,
    rank_tolerance: Real = 1e-12,
) -> SVDReport:
    source = finite_matrix("matrix", matrix)
    rows = len(source)
    columns = len(source[0])
    tolerance = positive_scalar("rank_tolerance", rank_tolerance)
    transposed = transpose(source)
    gram = tuple(
        tuple(
            compensated_sum(transposed[i][k] * source[k][j] for k in range(rows))
            for j in range(columns)
        )
        for i in range(columns)
    )
    eig = symmetric_eigensystem(gram, tolerance=max(tolerance * tolerance, 1e-15))
    raw_values = []
    for index, eigenvalue in enumerate(eig.eigenvalues):
        scale = max(1.0, abs(eig.eigenvalues[0]) if eig.eigenvalues else 1.0)
        if eigenvalue < -tolerance * scale:
            raise MathInvariantError(
                "A^T A produced a materially negative eigenvalue",
                reason="numerical_invariant_failure",
                field=f"eigenvalues[{index}]",
            )
        raw_values.append(math.sqrt(max(0.0, eigenvalue)))
    maximum = max(raw_values, default=0.0)
    cutoff = tolerance * max(1.0, maximum)

    singular_values: list[float] = []
    left_vectors: list[Vector] = []
    right_vectors: list[Vector] = []
    for singular, right in zip(raw_values, eig.eigenvectors):
        if singular <= cutoff:
            continue
        image = matvec(source, right)
        left = tuple(value / singular for value in image)
        norm = math.sqrt(compensated_sum(value * value for value in left))
        if norm == 0.0 or not math.isfinite(norm):
            raise MathInvariantError(
                "SVD produced an invalid left singular vector",
                reason="numerical_invariant_failure",
                field="left_vectors",
            )
        left = tuple(value / norm for value in left)
        singular *= norm
        singular_values.append(singular)
        left_vectors.append(left)
        right_vectors.append(right)

    rank = len(singular_values)
    reconstruction = 0.0
    for i in range(rows):
        for j in range(columns):
            estimate = compensated_sum(
                singular_values[k] * left_vectors[k][i] * right_vectors[k][j]
                for k in range(rank)
            )
            reconstruction = max(reconstruction, abs(estimate - source[i][j]))
    condition = None
    if singular_values:
        condition = max(singular_values) / min(singular_values)
    return SVDReport(
        singular_values=tuple(singular_values),
        left_vectors=tuple(left_vectors),
        right_vectors=tuple(right_vectors),
        rank=rank,
        reconstruction_linf=reconstruction,
        condition_number=condition,
    )


@dataclass(frozen=True, slots=True)
class PseudoinverseReport:
    pseudoinverse: Matrix
    rank: int
    projection_residual_linf: float


def pseudoinverse(
    matrix: Sequence[Sequence[Real]],
    *,
    rank_tolerance: Real = 1e-12,
) -> PseudoinverseReport:
    source = finite_matrix("matrix", matrix)
    rows = len(source)
    columns = len(source[0])
    svd = singular_value_decomposition(source, rank_tolerance=rank_tolerance)
    inverse = tuple(
        tuple(
            compensated_sum(
                svd.right_vectors[k][i] * svd.left_vectors[k][j] / svd.singular_values[k]
                for k in range(svd.rank)
            )
            for j in range(rows)
        )
        for i in range(columns)
    )
    # Moore-Penrose reconstruction identity A A+ A ~= A.
    first = tuple(
        tuple(
            compensated_sum(source[i][k] * inverse[k][j] for k in range(columns))
            for j in range(rows)
        )
        for i in range(rows)
    )
    projected = tuple(
        tuple(
            compensated_sum(first[i][k] * source[k][j] for k in range(rows))
            for j in range(columns)
        )
        for i in range(rows)
    )
    residual = max(
        abs(projected[i][j] - source[i][j])
        for i in range(rows)
        for j in range(columns)
    )
    return PseudoinverseReport(
        pseudoinverse=inverse,
        rank=svd.rank,
        projection_residual_linf=residual,
    )


def least_norm_solve(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    rank_tolerance: Real = 1e-12,
) -> Vector:
    source = finite_matrix("matrix", matrix)
    target = finite_vector("rhs", rhs)
    if len(target) != len(source):
        raise MathInvariantError(
            "least-norm rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    report = pseudoinverse(source, rank_tolerance=rank_tolerance)
    return matvec(report.pseudoinverse, target)
