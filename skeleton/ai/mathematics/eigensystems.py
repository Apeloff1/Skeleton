"""Full symmetric eigensystem and PCA reference diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .linear import dot, l2_norm
from .numerics import compensated_sum


@dataclass(frozen=True, slots=True)
class SymmetricEigensystemReport:
    eigenvalues: Vector
    eigenvectors: Matrix
    sweeps: int
    converged: bool
    off_diagonal_linf: float
    orthogonality_linf: float
    reconstruction_linf: float


def symmetric_eigensystem(
    matrix: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-12,
    max_sweeps: int = 100,
    symmetry_tolerance: Real = 1e-12,
) -> SymmetricEigensystemReport:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "symmetric eigensystem requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    tol = positive_scalar("tolerance", tolerance)
    sym_tol = positive_scalar("symmetry_tolerance", symmetry_tolerance)
    if isinstance(max_sweeps, bool) or not isinstance(max_sweeps, int) or max_sweeps < 1:
        raise MathInvariantError(
            "max_sweeps must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_sweeps",
        )
    scale = max(1.0, max(abs(value) for row in source for value in row))
    for i in range(n):
        for j in range(i + 1, n):
            if abs(source[i][j] - source[j][i]) > sym_tol * scale:
                raise MathInvariantError(
                    "symmetric eigensystem requires a symmetric matrix",
                    reason="non_symmetric_matrix",
                    field="matrix",
                )

    work = [list(row) for row in source]
    vectors = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    converged = n <= 1
    sweeps = 0

    for sweeps in range(1, max_sweeps + 1):
        largest = 0.0
        pivot_p = 0
        pivot_q = 0
        for p in range(n):
            for q in range(p + 1, n):
                magnitude = abs(work[p][q])
                if magnitude > largest:
                    largest = magnitude
                    pivot_p, pivot_q = p, q
        if largest <= tol * scale:
            converged = True
            break

        p, q = pivot_p, pivot_q
        app = work[p][p]
        aqq = work[q][q]
        apq = work[p][q]
        if apq == 0.0:
            continue
        tau = (aqq - app) / (2.0 * apq)
        t = math.copysign(1.0, tau) / (abs(tau) + math.sqrt(1.0 + tau * tau)) if tau != 0.0 else 1.0
        c = 1.0 / math.sqrt(1.0 + t * t)
        s = t * c

        for k in range(n):
            if k in (p, q):
                continue
            wkp = work[k][p]
            wkq = work[k][q]
            new_kp = c * wkp - s * wkq
            new_kq = s * wkp + c * wkq
            work[k][p] = work[p][k] = new_kp
            work[k][q] = work[q][k] = new_kq

        work[p][p] = app - t * apq
        work[q][q] = aqq + t * apq
        work[p][q] = work[q][p] = 0.0

        for k in range(n):
            vkp = vectors[k][p]
            vkq = vectors[k][q]
            vectors[k][p] = c * vkp - s * vkq
            vectors[k][q] = s * vkp + c * vkq

    eigenpairs = []
    for column in range(n):
        vector = tuple(vectors[row][column] for row in range(n))
        norm = l2_norm(vector)
        if norm == 0.0:
            raise MathInvariantError(
                "eigensystem produced zero eigenvector",
                reason="numerical_invariant_failure",
                field="eigenvectors",
            )
        vector = tuple(value / norm for value in vector)
        pivot = max(range(n), key=lambda index: abs(vector[index]))
        if vector[pivot] < 0.0:
            vector = tuple(-value for value in vector)
        eigenpairs.append((work[column][column], vector))
    eigenpairs.sort(key=lambda pair: (-pair[0], pair[1]))
    eigenvalues = tuple(pair[0] for pair in eigenpairs)
    eigenvectors = tuple(pair[1] for pair in eigenpairs)

    off_diagonal = max(
        (abs(work[i][j]) for i in range(n) for j in range(n) if i != j),
        default=0.0,
    )
    orthogonality = 0.0
    for i in range(n):
        for j in range(n):
            target = 1.0 if i == j else 0.0
            orthogonality = max(
                orthogonality,
                abs(dot(eigenvectors[i], eigenvectors[j]) - target),
            )
    reconstruction = 0.0
    for row in range(n):
        for column in range(n):
            estimate = compensated_sum(
                eigenvalues[k] * eigenvectors[k][row] * eigenvectors[k][column]
                for k in range(n)
            )
            reconstruction = max(reconstruction, abs(estimate - source[row][column]))

    return SymmetricEigensystemReport(
        eigenvalues=eigenvalues,
        eigenvectors=eigenvectors,
        sweeps=sweeps,
        converged=converged,
        off_diagonal_linf=off_diagonal,
        orthogonality_linf=orthogonality,
        reconstruction_linf=reconstruction,
    )


@dataclass(frozen=True, slots=True)
class PCAReport:
    mean: Vector
    components: Matrix
    eigenvalues: Vector
    explained_variance_ratio: Vector
    transformed: Matrix
    reconstruction_linf: float


def principal_components(
    observations: Sequence[Sequence[Real]],
    *,
    components: int | None = None,
    sample_covariance: bool = True,
    tolerance: Real = 1e-12,
) -> PCAReport:
    if not observations:
        raise MathInvariantError(
            "PCA requires observations",
            reason="empty_matrix",
            field="observations",
        )
    rows = tuple(finite_vector(f"observations[{i}]", row) for i, row in enumerate(observations))
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise MathInvariantError(
            "PCA observations must be rectangular",
            reason="ragged_matrix",
            field="observations",
        )
    if sample_covariance and len(rows) < 2:
        raise MathInvariantError(
            "sample PCA requires at least two observations",
            reason="insufficient_observations",
            field="observations",
        )
    count = width if components is None else components
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= width:
        raise MathInvariantError(
            "PCA component count is out of range",
            reason="invalid_component_count",
            field="components",
        )
    mean = tuple(
        compensated_sum(row[column] for row in rows) / len(rows)
        for column in range(width)
    )
    centered = tuple(
        tuple(value - mean[column] for column, value in enumerate(row))
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
    selected_values = eig.eigenvalues[:count]
    selected_vectors = eig.eigenvectors[:count]
    positive_total = compensated_sum(max(0.0, value) for value in eig.eigenvalues)
    ratios = tuple(
        0.0 if positive_total == 0.0 else max(0.0, value) / positive_total
        for value in selected_values
    )
    transformed = tuple(
        tuple(dot(row, component) for component in selected_vectors)
        for row in centered
    )
    reconstruction_error = 0.0
    for original, scores in zip(rows, transformed):
        reconstructed = tuple(
            mean[index] + compensated_sum(
                score * selected_vectors[k][index]
                for k, score in enumerate(scores)
            )
            for index in range(width)
        )
        reconstruction_error = max(
            reconstruction_error,
            max(abs(a - b) for a, b in zip(original, reconstructed)),
        )
    return PCAReport(
        mean=mean,
        components=selected_vectors,
        eigenvalues=selected_values,
        explained_variance_ratio=ratios,
        transformed=transformed,
        reconstruction_linf=reconstruction_error,
    )
