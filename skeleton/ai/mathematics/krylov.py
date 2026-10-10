"""Arnoldi and unrestarted GMRES reference solvers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .linear import dot, l2_norm, matvec


@dataclass(frozen=True, slots=True)
class ArnoldiReport:
    basis: tuple[Vector, ...]
    hessenberg: Matrix
    steps: int
    breakdown: bool
    orthogonality_linf: float


def _square_matrix(matrix: Sequence[Sequence[Real]]) -> Matrix:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "Krylov methods require a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    return source


def arnoldi_iteration(
    matrix: Sequence[Sequence[Real]],
    start: Sequence[Real],
    *,
    steps: int,
    breakdown_tolerance: Real = 1e-14,
) -> ArnoldiReport:
    source = _square_matrix(matrix)
    vector = finite_vector("start", start)
    n = len(source)
    if len(vector) != n:
        raise MathInvariantError(
            "Arnoldi start dimension mismatch",
            reason="dimension_mismatch",
            field="start",
        )
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= n:
        raise MathInvariantError(
            "Arnoldi steps must be an integer in [1, matrix size]",
            reason="invalid_iteration_limit",
            field="steps",
        )
    tolerance = positive_scalar("breakdown_tolerance", breakdown_tolerance)
    norm = l2_norm(vector)
    if norm == 0.0:
        raise MathInvariantError(
            "Arnoldi start vector must be non-zero",
            reason="zero_norm",
            field="start",
        )
    basis: list[Vector] = [tuple(value / norm for value in vector)]
    h = [[0.0] * steps for _ in range(steps + 1)]
    actual = 0
    breakdown = False

    for column in range(steps):
        work = matvec(source, basis[column])
        for row in range(column + 1):
            coefficient = dot(basis[row], work)
            h[row][column] += coefficient
            work = tuple(
                value - coefficient * direction
                for value, direction in zip(work, basis[row])
            )
        # A second orthogonalization pass makes this a better reference oracle.
        for row in range(column + 1):
            correction = dot(basis[row], work)
            h[row][column] += correction
            work = tuple(
                value - correction * direction
                for value, direction in zip(work, basis[row])
            )
        next_norm = l2_norm(work)
        h[column + 1][column] = next_norm
        actual = column + 1
        if next_norm <= tolerance:
            breakdown = True
            break
        if column + 1 < steps:
            basis.append(tuple(value / next_norm for value in work))

    width = actual
    row_count = min(len(basis) + (0 if breakdown else 1), actual + 1)
    hessenberg = tuple(
        tuple(h[row][column] for column in range(width))
        for row in range(row_count)
    )
    orthogonality = 0.0
    for i in range(len(basis)):
        for j in range(len(basis)):
            target = 1.0 if i == j else 0.0
            orthogonality = max(
                orthogonality,
                abs(dot(basis[i], basis[j]) - target),
            )
    return ArnoldiReport(
        basis=tuple(basis),
        hessenberg=hessenberg,
        steps=actual,
        breakdown=breakdown,
        orthogonality_linf=orthogonality,
    )


@dataclass(frozen=True, slots=True)
class GMRESReport:
    solution: Vector
    residual_l2: float
    iterations: int
    converged: bool
    reason: str


def gmres(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    initial: Sequence[Real] | None = None,
    absolute_tolerance: Real = 1e-12,
    relative_tolerance: Real = 1e-10,
    max_iterations: int | None = None,
) -> GMRESReport:
    source = _square_matrix(matrix)
    target = finite_vector("rhs", rhs)
    n = len(source)
    if len(target) != n:
        raise MathInvariantError(
            "GMRES rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    x0 = tuple(0.0 for _ in range(n)) if initial is None else finite_vector("initial", initial)
    if len(x0) != n:
        raise MathInvariantError(
            "GMRES initial dimension mismatch",
            reason="dimension_mismatch",
            field="initial",
        )
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    limit = n if max_iterations is None else max_iterations
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= n:
        raise MathInvariantError(
            "unrestarted GMRES max_iterations must lie in [1, matrix size]",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    residual = tuple(b - a for b, a in zip(target, matvec(source, x0)))
    beta = l2_norm(residual)
    threshold = max(abs_tol, rel_tol * l2_norm(target))
    if beta <= threshold:
        return GMRESReport(x0, beta, 0, True, "initial_residual")

    basis: list[Vector] = [tuple(value / beta for value in residual)]
    h = [[0.0] * limit for _ in range(limit + 1)]
    cosines = [0.0] * limit
    sines = [0.0] * limit
    g = [0.0] * (limit + 1)
    g[0] = beta
    completed = 0
    reason = "iteration_limit"

    for column in range(limit):
        work = matvec(source, basis[column])
        for row in range(column + 1):
            h[row][column] = dot(basis[row], work)
            work = tuple(
                value - h[row][column] * direction
                for value, direction in zip(work, basis[row])
            )
        # Re-orthogonalize once.
        for row in range(column + 1):
            correction = dot(basis[row], work)
            h[row][column] += correction
            work = tuple(
                value - correction * direction
                for value, direction in zip(work, basis[row])
            )
        h[column + 1][column] = l2_norm(work)
        happy_breakdown = h[column + 1][column] <= 1e-14

        for row in range(column):
            upper = cosines[row] * h[row][column] + sines[row] * h[row + 1][column]
            lower = -sines[row] * h[row][column] + cosines[row] * h[row + 1][column]
            h[row][column], h[row + 1][column] = upper, lower

        denominator = math.hypot(h[column][column], h[column + 1][column])
        if denominator == 0.0:
            completed = column
            reason = "krylov_breakdown"
            break
        cosines[column] = h[column][column] / denominator
        sines[column] = h[column + 1][column] / denominator
        h[column][column] = denominator
        h[column + 1][column] = 0.0

        upper_g = cosines[column] * g[column] + sines[column] * g[column + 1]
        lower_g = -sines[column] * g[column] + cosines[column] * g[column + 1]
        g[column], g[column + 1] = upper_g, lower_g
        completed = column + 1

        if abs(g[column + 1]) <= threshold:
            reason = "residual_tolerance"
            break
        if happy_breakdown:
            reason = "happy_breakdown"
            break
        if column + 1 < limit:
            basis.append(tuple(value / l2_norm(work) for value in work))

    if completed == 0:
        return GMRESReport(x0, beta, 0, False, reason)

    y = [0.0] * completed
    for row in range(completed - 1, -1, -1):
        diagonal = h[row][row]
        if abs(diagonal) <= 1e-15:
            raise MathInvariantError(
                "GMRES Hessenberg factor is singular",
                reason="singular_krylov_system",
                field="hessenberg",
            )
        correction = sum(h[row][column] * y[column] for column in range(row + 1, completed))
        y[row] = (g[row] - correction) / diagonal

    solution = tuple(
        x0[index] + sum(y[k] * basis[k][index] for k in range(completed))
        for index in range(n)
    )
    final_residual = l2_norm(
        tuple(b - a for b, a in zip(target, matvec(source, solution)))
    )
    converged = final_residual <= threshold
    return GMRESReport(
        solution=solution,
        residual_l2=final_residual,
        iterations=completed,
        converged=converged,
        reason=reason if converged else "iteration_limit",
    )
