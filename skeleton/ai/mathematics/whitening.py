"""Covariance whitening transforms with explicit covariance evidence."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector
from .eigensystems import symmetric_eigensystem
from .linear import dot
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class WhiteningReport:
    mean: Vector
    whitening_matrix: Matrix
    transformed: Matrix
    eigenvalues: Vector
    mode: str
    regularization: float
    covariance_residual_linf: float


def whiten(
    observations: Sequence[Sequence[Real]],
    *,
    mode: str = "zca",
    regularization: Real = 0.0,
    sample_covariance: bool = True,
    eigen_tolerance: Real = 1e-12,
) -> WhiteningReport:
    if not observations:
        raise MathInvariantError(
            "whitening requires observations",
            reason="empty_matrix",
            field="observations",
        )
    rows = tuple(
        finite_vector(f"observations[{index}]", row)
        for index, row in enumerate(observations)
    )
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise MathInvariantError(
            "whitening observations must be rectangular",
            reason="ragged_matrix",
            field="observations",
        )
    if mode not in {"pca", "zca"}:
        raise MathInvariantError(
            "whitening mode must be 'pca' or 'zca'",
            reason="invalid_whitening_mode",
            field="mode",
        )
    reg = finite_scalar("regularization", regularization)
    if reg < 0.0:
        raise MathInvariantError(
            "whitening regularization must be non-negative",
            reason="negative_regularization",
            field="regularization",
        )
    tolerance = finite_scalar("eigen_tolerance", eigen_tolerance)
    if tolerance <= 0.0:
        raise MathInvariantError(
            "eigen_tolerance must be positive",
            reason="invalid_tolerance",
            field="eigen_tolerance",
        )
    if sample_covariance and len(rows) < 2:
        raise MathInvariantError(
            "sample whitening requires at least two observations",
            reason="insufficient_observations",
            field="observations",
        )

    mean = tuple(
        compensated_sum(row[column] for row in rows) / len(rows)
        for column in range(width)
    )
    centered = tuple(
        tuple(row[column] - mean[column] for column in range(width))
        for row in rows
    )
    denominator = len(rows) - 1 if sample_covariance else len(rows)
    covariance = tuple(
        tuple(
            compensated_sum(row[i] * row[j] for row in centered) / denominator
            for j in range(width)
        )
        for i in range(width)
    )
    eig = symmetric_eigensystem(covariance, tolerance=tolerance)
    adjusted = tuple(value + reg for value in eig.eigenvalues)
    scale = max(1.0, max(abs(value) for value in eig.eigenvalues))
    if any(value <= tolerance * scale for value in adjusted):
        raise MathInvariantError(
            "whitening covariance is rank deficient; positive regularization is required",
            reason="rank_deficient_covariance",
            field="regularization",
        )
    inverse_roots = tuple(1.0 / math.sqrt(value) for value in adjusted)

    if mode == "pca":
        whitening_matrix = tuple(
            tuple(inverse_roots[row] * eig.eigenvectors[row][column] for column in range(width))
            for row in range(width)
        )
        transformed = tuple(
            tuple(
                inverse_roots[index] * dot(eig.eigenvectors[index], row)
                for index in range(width)
            )
            for row in centered
        )
    else:
        whitening_matrix = tuple(
            tuple(
                compensated_sum(
                    eig.eigenvectors[k][i]
                    * inverse_roots[k]
                    * eig.eigenvectors[k][j]
                    for k in range(width)
                )
                for j in range(width)
            )
            for i in range(width)
        )
        transformed = tuple(
            tuple(
                compensated_sum(row[j] * whitening_matrix[i][j] for j in range(width))
                for i in range(width)
            )
            for row in centered
        )

    whitened_covariance = tuple(
        tuple(
            compensated_sum(row[i] * row[j] for row in transformed) / denominator
            for j in range(width)
        )
        for i in range(width)
    )
    # With regularization, W C W^T = I - regularization * W W^T rather than I.
    target_covariance = tuple(
        tuple(
            compensated_sum(
                eig.eigenvectors[k][i]
                * (eig.eigenvalues[k] / adjusted[k])
                * eig.eigenvectors[k][j]
                for k in range(width)
            )
            if mode == "zca"
            else ((eig.eigenvalues[i] / adjusted[i]) if i == j else 0.0)
            for j in range(width)
        )
        for i in range(width)
    )
    residual = max(
        abs(whitened_covariance[i][j] - target_covariance[i][j])
        for i in range(width)
        for j in range(width)
    )
    return WhiteningReport(
        mean=mean,
        whitening_matrix=whitening_matrix,
        transformed=transformed,
        eigenvalues=eig.eigenvalues,
        mode=mode,
        regularization=reg,
        covariance_residual_linf=residual,
    )
