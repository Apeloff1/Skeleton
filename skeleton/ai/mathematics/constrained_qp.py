"""Convex quadratic-programming KKT and box active-set reference solvers."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .eigensystems import symmetric_eigensystem
from .linear import matvec, solve_linear_system
from .numerics import compensated_sum


def _quadratic(
    hessian: Sequence[Sequence[Real]],
    linear: Sequence[Real],
) -> tuple[Matrix, Vector]:
    h = finite_matrix("hessian", hessian)
    g = finite_vector("linear", linear)
    n = len(h)
    if len(h[0]) != n or len(g) != n:
        raise MathInvariantError(
            "quadratic objective dimensions must align",
            reason="dimension_mismatch",
            field="objective",
        )
    for i in range(n):
        for j in range(i + 1, n):
            if abs(h[i][j] - h[j][i]) > 1e-12:
                raise MathInvariantError(
                    "quadratic Hessian must be symmetric",
                    reason="non_symmetric_matrix",
                    field="hessian",
                )
    eig = symmetric_eigensystem(h)
    scale = max(1.0, max(abs(value) for value in eig.eigenvalues))
    if min(eig.eigenvalues) < -1e-12 * scale:
        raise MathInvariantError(
            "reference QP requires a positive-semidefinite Hessian",
            reason="non_convex_objective",
            field="hessian",
        )
    return h, g


def quadratic_objective(hessian: Matrix, linear: Vector, point: Vector) -> float:
    image = matvec(hessian, point)
    return 0.5 * compensated_sum(point[i] * image[i] for i in range(len(point))) + compensated_sum(
        linear[i] * point[i] for i in range(len(point))
    )


@dataclass(frozen=True, slots=True)
class EqualityQPReport:
    solution: Vector
    multipliers: Vector
    objective: float
    primal_residual_linf: float
    stationarity_residual_linf: float


def solve_equality_constrained_qp(
    hessian: Sequence[Sequence[Real]],
    linear: Sequence[Real],
    constraints: Sequence[Sequence[Real]],
    rhs: Sequence[Real],
) -> EqualityQPReport:
    h, g = _quadratic(hessian, linear)
    a = finite_matrix("constraints", constraints)
    b = finite_vector("rhs", rhs)
    n = len(h)
    m = len(a)
    if len(a[0]) != n or len(b) != m:
        raise MathInvariantError(
            "equality constraints must have shape (m, n) with matching rhs",
            reason="dimension_mismatch",
            field="constraints",
        )
    kkt = []
    target = []
    for i in range(n):
        kkt.append(tuple(h[i]) + tuple(a[row][i] for row in range(m)))
        target.append(-g[i])
    for row in range(m):
        kkt.append(tuple(a[row]) + tuple(0.0 for _ in range(m)))
        target.append(b[row])
    solved = solve_linear_system(tuple(kkt), tuple(target)).solution
    x = tuple(solved[:n])
    multipliers = tuple(solved[n:])
    primal = max(
        abs(compensated_sum(a[row][column] * x[column] for column in range(n)) - b[row])
        for row in range(m)
    )
    gradient = tuple(matvec(h, x)[i] + g[i] for i in range(n))
    stationarity = max(
        abs(
            gradient[i]
            + compensated_sum(a[row][i] * multipliers[row] for row in range(m))
        )
        for i in range(n)
    )
    return EqualityQPReport(
        solution=x,
        multipliers=multipliers,
        objective=quadratic_objective(h, g, x),
        primal_residual_linf=primal,
        stationarity_residual_linf=stationarity,
    )


@dataclass(frozen=True, slots=True)
class BoxQPReport:
    solution: Vector
    objective: float
    iterations: int
    converged: bool
    active_lower: tuple[int, ...]
    active_upper: tuple[int, ...]
    projected_gradient_linf: float


def solve_box_quadratic_active_set(
    hessian: Sequence[Sequence[Real]],
    linear: Sequence[Real],
    lower: Sequence[Real],
    upper: Sequence[Real],
    *,
    tolerance: Real = 1e-10,
    max_iterations: int = 200,
) -> BoxQPReport:
    h, g = _quadratic(hessian, linear)
    lo = finite_vector("lower", lower)
    hi = finite_vector("upper", upper)
    n = len(h)
    if len(lo) != n or len(hi) != n:
        raise MathInvariantError(
            "box bounds must match objective dimension",
            reason="dimension_mismatch",
            field="bounds",
        )
    if any(lo[i] > hi[i] for i in range(n)):
        raise MathInvariantError(
            "box lower bound must not exceed upper bound",
            reason="invalid_interval",
            field="bounds",
        )
    tol = positive_scalar("tolerance", tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    x = [0.5 * (lo[i] + hi[i]) for i in range(n)]
    active_lower = {i for i in range(n) if lo[i] == hi[i]}
    active_upper: set[int] = set()

    def projected_gradient(gradient: Vector) -> float:
        values = []
        for i, value in enumerate(gradient):
            if i in active_lower:
                values.append(min(0.0, value))
            elif i in active_upper:
                values.append(max(0.0, value))
            else:
                values.append(value)
        return max(abs(value) for value in values)

    for iteration in range(1, max_iterations + 1):
        for i in active_lower:
            x[i] = lo[i]
        for i in active_upper:
            x[i] = hi[i]
        free = [i for i in range(n) if i not in active_lower and i not in active_upper]
        if free:
            reduced = tuple(tuple(h[i][j] for j in free) for i in free)
            rhs = tuple(
                -g[i]
                - compensated_sum(h[i][j] * x[j] for j in active_lower)
                - compensated_sum(h[i][j] * x[j] for j in active_upper)
                for i in free
            )
            try:
                solved = solve_linear_system(reduced, rhs).solution
            except MathInvariantError as error:
                raise MathInvariantError(
                    "free-set QP system is singular; unique active-set step unavailable",
                    reason="singular_active_set",
                    field="hessian",
                ) from error
            for index, value in zip(free, solved):
                x[index] = value

        clipped = False
        for i in tuple(free):
            if x[i] < lo[i]:
                x[i] = lo[i]
                active_lower.add(i)
                clipped = True
            elif x[i] > hi[i]:
                x[i] = hi[i]
                active_upper.add(i)
                clipped = True
        if clipped:
            continue

        gradient = tuple(matvec(h, tuple(x))[i] + g[i] for i in range(n))
        release_lower = [i for i in active_lower if lo[i] != hi[i] and gradient[i] < -tol]
        release_upper = [i for i in active_upper if gradient[i] > tol]
        if release_lower:
            active_lower.remove(min(release_lower, key=lambda i: gradient[i]))
            continue
        if release_upper:
            active_upper.remove(max(release_upper, key=lambda i: gradient[i]))
            continue

        pg = projected_gradient(gradient)
        if pg <= tol:
            solution = tuple(x)
            return BoxQPReport(
                solution=solution,
                objective=quadratic_objective(h, g, solution),
                iterations=iteration,
                converged=True,
                active_lower=tuple(sorted(active_lower)),
                active_upper=tuple(sorted(active_upper)),
                projected_gradient_linf=pg,
            )

    gradient = tuple(matvec(h, tuple(x))[i] + g[i] for i in range(n))
    solution = tuple(x)
    return BoxQPReport(
        solution=solution,
        objective=quadratic_objective(h, g, solution),
        iterations=max_iterations,
        converged=False,
        active_lower=tuple(sorted(active_lower)),
        active_upper=tuple(sorted(active_upper)),
        projected_gradient_linf=projected_gradient(gradient),
    )
