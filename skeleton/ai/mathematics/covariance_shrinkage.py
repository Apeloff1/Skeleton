"""Covariance shrinkage and Oracle Approximating Shrinkage references."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_scalar, finite_vector
from .eigensystems import symmetric_eigensystem
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class CovarianceShrinkageReport:
    covariance: Matrix
    shrunk_covariance: Matrix
    intensity: float
    target: str
    mean: Vector | None
    minimum_eigenvalue: float
    maximum_eigenvalue: float
    spectral_condition: float


def shrink_covariance(
    covariance: Sequence[Sequence[Real]],
    intensity: Real,
    *,
    target: str = "identity",
) -> CovarianceShrinkageReport:
    source = finite_matrix("covariance", covariance)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "covariance shrinkage requires a square matrix",
            reason="non_square_matrix",
            field="covariance",
        )
    amount = finite_scalar("intensity", intensity)
    if not 0.0 <= amount <= 1.0:
        raise MathInvariantError(
            "shrinkage intensity must lie in [0, 1]",
            reason="invalid_probability",
            field="intensity",
        )
    if target not in {"identity", "diagonal"}:
        raise MathInvariantError(
            "shrinkage target must be identity or diagonal",
            reason="invalid_shrinkage_target",
            field="target",
        )
    for i in range(n):
        for j in range(i + 1, n):
            if abs(source[i][j] - source[j][i]) > 1e-12:
                raise MathInvariantError(
                    "covariance shrinkage requires a symmetric matrix",
                    reason="non_symmetric_matrix",
                    field="covariance",
                )
    mean_variance = compensated_sum(source[i][i] for i in range(n)) / n
    if mean_variance < 0.0:
        raise MathInvariantError(
            "covariance diagonal has negative mean variance",
            reason="invalid_covariance",
            field="covariance",
        )
    result = []
    for i in range(n):
        row = []
        for j in range(n):
            if target == "identity":
                target_value = mean_variance if i == j else 0.0
            else:
                target_value = source[i][i] if i == j else 0.0
            row.append((1.0 - amount) * source[i][j] + amount * target_value)
        result.append(tuple(row))
    shrunk = tuple(result)
    eig = symmetric_eigensystem(shrunk)
    minimum = min(eig.eigenvalues)
    maximum = max(eig.eigenvalues)
    condition = float("inf") if minimum <= 0.0 else maximum / minimum
    return CovarianceShrinkageReport(
        covariance=source,
        shrunk_covariance=shrunk,
        intensity=amount,
        target=target,
        mean=None,
        minimum_eigenvalue=minimum,
        maximum_eigenvalue=maximum,
        spectral_condition=condition,
    )


def oracle_approximating_shrinkage(
    observations: Sequence[Sequence[Real]],
) -> CovarianceShrinkageReport:
    if not observations:
        raise MathInvariantError(
            "OAS requires observations",
            reason="empty_matrix",
            field="observations",
        )
    rows = tuple(
        finite_vector(f"observations[{index}]", row)
        for index, row in enumerate(observations)
    )
    features = len(rows[0])
    if any(len(row) != features for row in rows):
        raise MathInvariantError(
            "OAS observations must be rectangular",
            reason="ragged_matrix",
            field="observations",
        )
    samples = len(rows)
    if samples < 2:
        raise MathInvariantError(
            "OAS requires at least two observations",
            reason="insufficient_observations",
            field="observations",
        )
    mean = tuple(
        compensated_sum(row[column] for row in rows) / samples
        for column in range(features)
    )
    centered = tuple(
        tuple(row[column] - mean[column] for column in range(features))
        for row in rows
    )
    covariance = tuple(
        tuple(
            compensated_sum(row[i] * row[j] for row in centered) / samples
            for j in range(features)
        )
        for i in range(features)
    )
    mu = compensated_sum(covariance[i][i] for i in range(features)) / features
    alpha = compensated_sum(
        value * value for row in covariance for value in row
    ) / (features * features)
    numerator = alpha + mu * mu
    denominator = (samples + 1.0) * (alpha - (mu * mu) / features)
    intensity = 1.0 if denominator <= 0.0 else min(1.0, max(0.0, numerator / denominator))
    base = shrink_covariance(covariance, intensity, target="identity")
    return CovarianceShrinkageReport(
        covariance=base.covariance,
        shrunk_covariance=base.shrunk_covariance,
        intensity=base.intensity,
        target="oas_identity",
        mean=mean,
        minimum_eigenvalue=base.minimum_eigenvalue,
        maximum_eigenvalue=base.maximum_eigenvalue,
        spectral_condition=base.spectral_condition,
    )
