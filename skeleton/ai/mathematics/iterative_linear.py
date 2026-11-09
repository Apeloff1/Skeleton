"""Stationary iterative linear-system reference solvers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .linear import l2_norm, matvec


@dataclass(frozen=True, slots=True)
class StationaryIterationReport:
    solution: Vector
    residual_l2: float
    iterations: int
    converged: bool
    method: str


def _system(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    initial: Sequence[Real] | None,
) -> tuple[Matrix, Vector, Vector]:
    source = finite_matrix("matrix", matrix)
    n = len(source)
    if len(source[0]) != n:
        raise MathInvariantError(
            "stationary iteration requires a square matrix",
            reason="non_square_matrix",
            field="matrix",
        )
    target = finite_vector("rhs", rhs)
    if len(target) != n:
        raise MathInvariantError(
            "stationary iteration rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    guess = tuple(0.0 for _ in range(n)) if initial is None else finite_vector("initial", initial)
    if len(guess) != n:
        raise MathInvariantError(
            "stationary iteration initial dimension mismatch",
            reason="dimension_mismatch",
            field="initial",
        )
    for index in range(n):
        if source[index][index] == 0.0:
            raise MathInvariantError(
                "stationary iteration requires non-zero diagonal entries",
                reason="zero_diagonal",
                field=f"matrix[{index}][{index}]",
            )
    return source, target, guess


def _residual_l2(matrix: Matrix, solution: Vector, rhs: Vector) -> float:
    image = matvec(matrix, solution)
    return l2_norm(tuple(target - value for target, value in zip(rhs, image)))


def jacobi_solve(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    initial: Sequence[Real] | None = None,
    absolute_tolerance: Real = 1e-12,
    relative_tolerance: Real = 1e-10,
    max_iterations: int = 10000,
) -> StationaryIterationReport:
    source, target, current = _system(matrix, rhs, initial)
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    threshold = max(abs_tol, rel_tol * l2_norm(target))
    residual = _residual_l2(source, current, target)
    if residual <= threshold:
        return StationaryIterationReport(current, residual, 0, True, "jacobi")

    for iteration in range(1, max_iterations + 1):
        candidate = []
        for i, row in enumerate(source):
            correction = sum(row[j] * current[j] for j in range(len(row)) if j != i)
            value = (target[i] - correction) / row[i]
            if not math.isfinite(value):
                raise MathInvariantError(
                    "Jacobi iteration produced non-finite value",
                    reason="non_finite_result",
                    field="solution",
                )
            candidate.append(value)
        current = tuple(candidate)
        residual = _residual_l2(source, current, target)
        if residual <= threshold:
            return StationaryIterationReport(current, residual, iteration, True, "jacobi")
    return StationaryIterationReport(current, residual, max_iterations, False, "jacobi")


def gauss_seidel_solve(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    initial: Sequence[Real] | None = None,
    absolute_tolerance: Real = 1e-12,
    relative_tolerance: Real = 1e-10,
    max_iterations: int = 10000,
) -> StationaryIterationReport:
    source, target, start = _system(matrix, rhs, initial)
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    current = list(start)
    threshold = max(abs_tol, rel_tol * l2_norm(target))
    residual = _residual_l2(source, tuple(current), target)
    if residual <= threshold:
        return StationaryIterationReport(tuple(current), residual, 0, True, "gauss_seidel")

    for iteration in range(1, max_iterations + 1):
        for i, row in enumerate(source):
            correction = sum(row[j] * current[j] for j in range(len(row)) if j != i)
            value = (target[i] - correction) / row[i]
            if not math.isfinite(value):
                raise MathInvariantError(
                    "Gauss-Seidel iteration produced non-finite value",
                    reason="non_finite_result",
                    field="solution",
                )
            current[i] = value
        solution = tuple(current)
        residual = _residual_l2(source, solution, target)
        if residual <= threshold:
            return StationaryIterationReport(solution, residual, iteration, True, "gauss_seidel")
    return StationaryIterationReport(tuple(current), residual, max_iterations, False, "gauss_seidel")


def sor_solve(
    matrix: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
    *,
    omega: Real = 1.0,
    initial: Sequence[Real] | None = None,
    absolute_tolerance: Real = 1e-12,
    relative_tolerance: Real = 1e-10,
    max_iterations: int = 10000,
) -> StationaryIterationReport:
    source, target, start = _system(matrix, rhs, initial)
    relaxation = positive_scalar("omega", omega)
    if not 0.0 < relaxation < 2.0:
        raise MathInvariantError(
            "SOR omega must lie in (0, 2)",
            reason="invalid_relaxation",
            field="omega",
        )
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    current = list(start)
    threshold = max(abs_tol, rel_tol * l2_norm(target))
    residual = _residual_l2(source, tuple(current), target)
    if residual <= threshold:
        return StationaryIterationReport(tuple(current), residual, 0, True, "sor")

    for iteration in range(1, max_iterations + 1):
        previous = tuple(current)
        for i, row in enumerate(source):
            correction = sum(row[j] * current[j] for j in range(len(row)) if j != i)
            raw = (target[i] - correction) / row[i]
            current[i] = previous[i] + relaxation * (raw - previous[i])
            if not math.isfinite(current[i]):
                raise MathInvariantError(
                    "SOR iteration produced non-finite value",
                    reason="non_finite_result",
                    field="solution",
                )
        solution = tuple(current)
        residual = _residual_l2(source, solution, target)
        if residual <= threshold:
            return StationaryIterationReport(solution, residual, iteration, True, "sor")
    return StationaryIterationReport(tuple(current), residual, max_iterations, False, "sor")
