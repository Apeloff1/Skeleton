"""Iterative sparse linear solvers layered on canonical CSR storage."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector, positive_scalar
from .linear import dot, l2_norm
from .sparse import CSRMatrix


@dataclass(frozen=True, slots=True)
class SparseSolveReport:
    solution: Vector
    residual_l2: float
    relative_residual: float
    iterations: int
    converged: bool
    method: str
    preconditioned: bool


def jacobi_preconditioner(matrix: CSRMatrix) -> Vector:
    rows, columns = matrix.shape
    if rows != columns:
        raise MathInvariantError(
            "Jacobi preconditioner requires a square sparse matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    inverse = []
    for row in range(rows):
        diagonal = 0.0
        for offset in range(matrix.indptr[row], matrix.indptr[row + 1]):
            if matrix.indices[offset] == row:
                diagonal = matrix.data[offset]
                break
        if diagonal <= 0.0:
            raise MathInvariantError(
                "PCG Jacobi preconditioner requires positive diagonal entries",
                reason="non_positive_diagonal",
                field=f"matrix[{row}][{row}]",
            )
        inverse.append(1.0 / diagonal)
    return tuple(inverse)


def _validate_sparse_system(matrix: CSRMatrix, rhs: Sequence[Real], initial: Sequence[Real] | None) -> tuple[Vector, Vector]:
    rows, columns = matrix.shape
    if rows != columns:
        raise MathInvariantError(
            "iterative sparse solve requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    target = finite_vector("rhs", rhs)
    if len(target) != rows:
        raise MathInvariantError(
            "sparse rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    start = tuple(0.0 for _ in range(rows)) if initial is None else finite_vector("initial", initial)
    if len(start) != rows:
        raise MathInvariantError(
            "sparse initial dimension mismatch",
            reason="dimension_mismatch",
            field="initial",
        )
    return target, start


def preconditioned_conjugate_gradient(
    matrix: CSRMatrix,
    rhs: Sequence[Real],
    *,
    initial: Sequence[Real] | None = None,
    tolerance: Real = 1e-10,
    absolute_tolerance: Real = 1e-12,
    max_iterations: int | None = None,
    use_jacobi: bool = True,
) -> SparseSolveReport:
    target, start = _validate_sparse_system(matrix, rhs, initial)
    n = len(target)
    tol = positive_scalar("tolerance", tolerance)
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    limit = max(1, 2 * n) if max_iterations is None else max_iterations
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    # PCG is only valid for symmetric positive-definite systems. Symmetry is
    # checked explicitly; positive definiteness is guarded by p^T A p > 0.
    dense = matrix.to_dense()
    for i in range(n):
        for j in range(i + 1, n):
            if dense[i][j] != dense[j][i]:
                raise MathInvariantError(
                    "PCG requires an exactly symmetric CSR matrix",
                    reason="non_symmetric_matrix",
                    field="matrix",
                )

    preconditioner = jacobi_preconditioner(matrix) if use_jacobi else tuple(1.0 for _ in range(n))
    x = start
    ax = matrix.matvec(x)
    residual = tuple(target[i] - ax[i] for i in range(n))
    rhs_norm = l2_norm(target)
    threshold = max(abs_tol, tol * rhs_norm)
    residual_norm = l2_norm(residual)
    if residual_norm <= threshold:
        return SparseSolveReport(x, residual_norm, 0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm, 0, True, "pcg", use_jacobi)

    z = tuple(preconditioner[i] * residual[i] for i in range(n))
    direction = z
    rz = dot(residual, z)
    if rz <= 0.0:
        raise MathInvariantError(
            "PCG preconditioned residual inner product is not positive",
            reason="non_positive_definite_matrix",
            field="matrix",
        )

    for iteration in range(1, limit + 1):
        image = matrix.matvec(direction)
        curvature = dot(direction, image)
        if curvature <= 0.0 or not math.isfinite(curvature):
            raise MathInvariantError(
                "PCG encountered non-positive curvature",
                reason="non_positive_definite_matrix",
                field="matrix",
            )
        alpha = rz / curvature
        x = tuple(x[i] + alpha * direction[i] for i in range(n))
        residual = tuple(residual[i] - alpha * image[i] for i in range(n))
        residual_norm = l2_norm(residual)
        if residual_norm <= threshold:
            return SparseSolveReport(
                x,
                residual_norm,
                0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm,
                iteration,
                True,
                "pcg",
                use_jacobi,
            )
        z = tuple(preconditioner[i] * residual[i] for i in range(n))
        next_rz = dot(residual, z)
        if next_rz <= 0.0:
            raise MathInvariantError(
                "PCG preconditioned residual lost positive energy",
                reason="non_positive_definite_matrix",
                field="matrix",
            )
        beta = next_rz / rz
        direction = tuple(z[i] + beta * direction[i] for i in range(n))
        rz = next_rz

    return SparseSolveReport(
        x,
        residual_norm,
        0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm,
        limit,
        False,
        "pcg",
        use_jacobi,
    )


def bicgstab(
    matrix: CSRMatrix,
    rhs: Sequence[Real],
    *,
    initial: Sequence[Real] | None = None,
    tolerance: Real = 1e-10,
    absolute_tolerance: Real = 1e-12,
    max_iterations: int | None = None,
) -> SparseSolveReport:
    target, start = _validate_sparse_system(matrix, rhs, initial)
    n = len(target)
    tol = positive_scalar("tolerance", tolerance)
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    limit = max(1, 4 * n) if max_iterations is None else max_iterations
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    x = start
    initial_image = matrix.matvec(x)
    residual = tuple(target[i] - initial_image[i] for i in range(n))
    shadow = residual
    rhs_norm = l2_norm(target)
    threshold = max(abs_tol, tol * rhs_norm)
    residual_norm = l2_norm(residual)
    if residual_norm <= threshold:
        return SparseSolveReport(x, residual_norm, 0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm, 0, True, "bicgstab", False)

    rho_previous = alpha = omega = 1.0
    direction = tuple(0.0 for _ in range(n))
    v = tuple(0.0 for _ in range(n))

    for iteration in range(1, limit + 1):
        rho = dot(shadow, residual)
        if abs(rho) <= 1e-30:
            raise MathInvariantError(
                "BiCGSTAB shadow residual breakdown",
                reason="krylov_breakdown",
                field="residual",
            )
        beta = (rho / rho_previous) * (alpha / omega)
        direction = tuple(
            residual[i] + beta * (direction[i] - omega * v[i])
            for i in range(n)
        )
        v = matrix.matvec(direction)
        denominator = dot(shadow, v)
        if abs(denominator) <= 1e-30:
            raise MathInvariantError(
                "BiCGSTAB alpha denominator breakdown",
                reason="krylov_breakdown",
                field="matrix",
            )
        alpha = rho / denominator
        s = tuple(residual[i] - alpha * v[i] for i in range(n))
        if l2_norm(s) <= threshold:
            x = tuple(x[i] + alpha * direction[i] for i in range(n))
            residual_norm = l2_norm(s)
            return SparseSolveReport(x, residual_norm, 0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm, iteration, True, "bicgstab", False)

        t = matrix.matvec(s)
        tt = dot(t, t)
        if tt <= 1e-30:
            raise MathInvariantError(
                "BiCGSTAB omega denominator breakdown",
                reason="krylov_breakdown",
                field="matrix",
            )
        omega = dot(t, s) / tt
        if abs(omega) <= 1e-30:
            raise MathInvariantError(
                "BiCGSTAB omega breakdown",
                reason="krylov_breakdown",
                field="matrix",
            )
        x = tuple(x[i] + alpha * direction[i] + omega * s[i] for i in range(n))
        residual = tuple(s[i] - omega * t[i] for i in range(n))
        residual_norm = l2_norm(residual)
        if residual_norm <= threshold:
            return SparseSolveReport(x, residual_norm, 0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm, iteration, True, "bicgstab", False)
        rho_previous = rho

    return SparseSolveReport(x, residual_norm, 0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm, limit, False, "bicgstab", False)
