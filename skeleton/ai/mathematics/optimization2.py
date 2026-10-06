"""Deterministic second-order and quasi-Newton optimization references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .calculus2 import finite_difference_hessian
from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector, positive_scalar
from .decompositions import solve_cholesky
from .linear import dot, l2_norm
from .numerics import compensated_sum
from .optimization import finite_difference_gradient


Objective = Callable[[Vector], Real]
Gradient = Callable[[Vector], Sequence[Real]]
Hessian = Callable[[Vector], Sequence[Sequence[Real]]]


@dataclass(frozen=True, slots=True)
class AdvancedOptimizationStep:
    iteration: int
    point: Vector
    objective: float
    gradient_norm: float
    step_norm: float
    step_size: float
    method: str


@dataclass(frozen=True, slots=True)
class AdvancedOptimizationResult:
    point: Vector
    objective: float
    gradient: Vector
    iterations: int
    converged: bool
    reason: str
    trace: tuple[AdvancedOptimizationStep, ...]


def _objective(function: Objective, point: Vector) -> float:
    return finite_scalar("objective", function(point))


def _gradient(
    function: Objective,
    point: Vector,
    analytic: Gradient | None,
) -> Vector:
    if analytic is None:
        return finite_difference_gradient(function, point)
    result = finite_vector("gradient", analytic(point))
    if len(result) != len(point):
        raise MathInvariantError(
            "gradient dimension mismatch",
            reason="dimension_mismatch",
            field="gradient",
        )
    return result


def _backtracking(
    function: Objective,
    point: Vector,
    objective: float,
    gradient: Vector,
    direction: Vector,
    *,
    initial_step: float,
    armijo: float,
    shrink: float,
    minimum_step: float,
) -> tuple[Vector, float, float] | None:
    slope = dot(gradient, direction)
    if slope >= 0.0:
        return None
    step = initial_step
    while step >= minimum_step:
        candidate = tuple(value + step * delta for value, delta in zip(point, direction))
        candidate_objective = _objective(function, candidate)
        if candidate_objective <= objective + armijo * step * slope:
            return candidate, candidate_objective, step
        step *= shrink
    return None


def damped_newton(
    function: Objective,
    initial: Sequence[Real],
    *,
    gradient: Gradient | None = None,
    hessian: Hessian | None = None,
    gradient_tolerance: Real = 1e-8,
    max_iterations: int = 100,
    initial_step: Real = 1.0,
    armijo: Real = 1e-4,
    shrink: Real = 0.5,
    minimum_step: Real = 1e-12,
    damping: Real = 1e-8,
) -> AdvancedOptimizationResult:
    point = finite_vector("initial", initial)
    grad_tol = positive_scalar("gradient_tolerance", gradient_tolerance)
    step0 = positive_scalar("initial_step", initial_step)
    armijo_value = positive_scalar("armijo", armijo)
    if armijo_value >= 1.0:
        raise MathInvariantError(
            "armijo must lie in (0, 1)",
            reason="invalid_armijo_constant",
            field="armijo",
        )
    shrink_value = finite_scalar("shrink", shrink)
    min_step = positive_scalar("minimum_step", minimum_step)
    damping_value = positive_scalar("damping", damping)
    if not 0.0 < shrink_value < 1.0:
        raise MathInvariantError(
            "shrink must lie in (0, 1)",
            reason="invalid_backtrack_factor",
            field="shrink",
        )
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    trace: list[AdvancedOptimizationStep] = []

    for iteration in range(max_iterations + 1):
        value = _objective(function, point)
        grad = _gradient(function, point, gradient)
        grad_norm = l2_norm(grad)
        if grad_norm <= grad_tol:
            return AdvancedOptimizationResult(point, value, grad, iteration, True, "gradient_tolerance", tuple(trace))
        if iteration == max_iterations:
            return AdvancedOptimizationResult(point, value, grad, iteration, False, "iteration_limit", tuple(trace))

        if hessian is None:
            matrix = finite_difference_hessian(function, point).hessian
        else:
            rows = tuple(finite_vector(f"hessian[{i}]", row) for i, row in enumerate(hessian(point)))
            if len(rows) != len(point) or any(len(row) != len(point) for row in rows):
                raise MathInvariantError(
                    "Hessian dimension mismatch",
                    reason="dimension_mismatch",
                    field="hessian",
                )
            matrix = rows

        direction: Vector | None = None
        local_damping = damping_value
        for _ in range(12):
            regularized = tuple(
                tuple(
                    matrix[i][j] + (local_damping if i == j else 0.0)
                    for j in range(len(point))
                )
                for i in range(len(point))
            )
            try:
                candidate_direction = solve_cholesky(
                    regularized,
                    tuple(-value for value in grad),
                )
            except MathInvariantError:
                local_damping *= 10.0
                continue
            if dot(grad, candidate_direction) < 0.0:
                direction = candidate_direction
                break
            local_damping *= 10.0
        if direction is None:
            direction = tuple(-value for value in grad)

        accepted = _backtracking(
            function,
            point,
            value,
            grad,
            direction,
            initial_step=step0,
            armijo=armijo_value,
            shrink=shrink_value,
            minimum_step=min_step,
        )
        if accepted is None:
            return AdvancedOptimizationResult(point, value, grad, iteration, False, "line_search_exhausted", tuple(trace))
        candidate, candidate_value, step_size = accepted
        step_norm = l2_norm(tuple(a - b for a, b in zip(candidate, point)))
        trace.append(
            AdvancedOptimizationStep(
                iteration=iteration + 1,
                point=candidate,
                objective=candidate_value,
                gradient_norm=grad_norm,
                step_norm=step_norm,
                step_size=step_size,
                method="damped_newton",
            )
        )
        point = candidate

    raise AssertionError("unreachable")


def bfgs(
    function: Objective,
    initial: Sequence[Real],
    *,
    gradient: Gradient | None = None,
    gradient_tolerance: Real = 1e-8,
    max_iterations: int = 200,
    initial_step: Real = 1.0,
    armijo: Real = 1e-4,
    shrink: Real = 0.5,
    minimum_step: Real = 1e-12,
    curvature_floor: Real = 1e-12,
) -> AdvancedOptimizationResult:
    point = finite_vector("initial", initial)
    n = len(point)
    grad_tol = positive_scalar("gradient_tolerance", gradient_tolerance)
    step0 = positive_scalar("initial_step", initial_step)
    armijo_value = positive_scalar("armijo", armijo)
    if armijo_value >= 1.0:
        raise MathInvariantError(
            "armijo must lie in (0, 1)",
            reason="invalid_armijo_constant",
            field="armijo",
        )
    shrink_value = finite_scalar("shrink", shrink)
    min_step = positive_scalar("minimum_step", minimum_step)
    curvature = positive_scalar("curvature_floor", curvature_floor)
    if not 0.0 < shrink_value < 1.0:
        raise MathInvariantError(
            "shrink must lie in (0, 1)",
            reason="invalid_backtrack_factor",
            field="shrink",
        )
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    inverse = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    trace: list[AdvancedOptimizationStep] = []
    value = _objective(function, point)
    grad = _gradient(function, point, gradient)

    for iteration in range(max_iterations + 1):
        grad_norm = l2_norm(grad)
        if grad_norm <= grad_tol:
            return AdvancedOptimizationResult(point, value, grad, iteration, True, "gradient_tolerance", tuple(trace))
        if iteration == max_iterations:
            return AdvancedOptimizationResult(point, value, grad, iteration, False, "iteration_limit", tuple(trace))

        direction = tuple(
            -compensated_sum(inverse[i][j] * grad[j] for j in range(n))
            for i in range(n)
        )
        if dot(grad, direction) >= 0.0:
            direction = tuple(-value for value in grad)
            inverse = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

        accepted = _backtracking(
            function,
            point,
            value,
            grad,
            direction,
            initial_step=step0,
            armijo=armijo_value,
            shrink=shrink_value,
            minimum_step=min_step,
        )
        if accepted is None:
            return AdvancedOptimizationResult(point, value, grad, iteration, False, "line_search_exhausted", tuple(trace))
        candidate, candidate_value, step_size = accepted
        candidate_grad = _gradient(function, candidate, gradient)
        s = tuple(a - b for a, b in zip(candidate, point))
        y = tuple(a - b for a, b in zip(candidate_grad, grad))
        ys = dot(y, s)
        if ys > curvature * max(1.0, l2_norm(y) * l2_norm(s)):
            rho = 1.0 / ys
            hy = tuple(
                compensated_sum(inverse[i][j] * y[j] for j in range(n))
                for i in range(n)
            )
            yhy = dot(y, hy)
            factor = (1.0 + yhy * rho) * rho
            updated = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    updated[i][j] = (
                        inverse[i][j]
                        + factor * s[i] * s[j]
                        - rho * (s[i] * hy[j] + hy[i] * s[j])
                    )
            inverse = updated
        else:
            inverse = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

        trace.append(
            AdvancedOptimizationStep(
                iteration=iteration + 1,
                point=candidate,
                objective=candidate_value,
                gradient_norm=grad_norm,
                step_norm=l2_norm(s),
                step_size=step_size,
                method="bfgs",
            )
        )
        point, value, grad = candidate, candidate_value, candidate_grad

    raise AssertionError("unreachable")
