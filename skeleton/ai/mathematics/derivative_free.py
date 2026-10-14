"""Deterministic derivative-free optimization reference solvers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import l2_norm


ScalarObjective = Callable[[float], Real]
VectorObjective = Callable[[Vector], Real]


def _objective_value(name: str, value: Real) -> float:
    return finite_scalar(name, value)


@dataclass(frozen=True, slots=True)
class GoldenSectionReport:
    minimizer: float
    objective: float
    lower: float
    upper: float
    iterations: int
    converged: bool


def golden_section_minimize(
    objective: ScalarObjective,
    lower: Real,
    upper: Real,
    *,
    tolerance: Real = 1e-10,
    max_iterations: int = 512,
) -> GoldenSectionReport:
    a = finite_scalar("lower", lower)
    b = finite_scalar("upper", upper)
    if b <= a:
        raise MathInvariantError(
            "golden-section interval must satisfy lower < upper",
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
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    c = b - ratio * (b - a)
    d = a + ratio * (b - a)
    fc = _objective_value("objective", objective(c))
    fd = _objective_value("objective", objective(d))

    iterations = 0
    for iterations in range(1, max_iterations + 1):
        if abs(b - a) <= tol * max(1.0, abs(a), abs(b)):
            break
        if fc <= fd:
            b, d, fd = d, c, fc
            c = b - ratio * (b - a)
            fc = _objective_value("objective", objective(c))
        else:
            a, c, fc = c, d, fd
            d = a + ratio * (b - a)
            fd = _objective_value("objective", objective(d))
    minimizer = 0.5 * (a + b)
    value = _objective_value("objective", objective(minimizer))
    converged = abs(b - a) <= tol * max(1.0, abs(a), abs(b))
    return GoldenSectionReport(minimizer, value, a, b, iterations, converged)


@dataclass(frozen=True, slots=True)
class NelderMeadReport:
    solution: Vector
    objective: float
    iterations: int
    evaluations: int
    converged: bool
    simplex_diameter: float
    objective_spread: float


def nelder_mead(
    objective: VectorObjective,
    initial: Sequence[Real],
    *,
    initial_step: Real = 0.05,
    x_tolerance: Real = 1e-9,
    f_tolerance: Real = 1e-12,
    max_iterations: int = 2000,
) -> NelderMeadReport:
    start = finite_vector("initial", initial)
    step = positive_scalar("initial_step", initial_step)
    x_tol = positive_scalar("x_tolerance", x_tolerance)
    f_tol = positive_scalar("f_tolerance", f_tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    dimension = len(start)
    simplex = [start]
    for axis in range(dimension):
        point = list(start)
        point[axis] += step * max(1.0, abs(start[axis]))
        simplex.append(tuple(point))

    evaluations = 0
    values = []
    for point in simplex:
        values.append(_objective_value("objective", objective(point)))
        evaluations += 1

    alpha = 1.0
    gamma = 2.0
    rho = 0.5
    sigma = 0.5
    converged = False
    diameter = math.inf
    spread = math.inf
    iterations = 0

    def distance(left: Vector, right: Vector) -> float:
        return l2_norm(tuple(a - b for a, b in zip(left, right)))

    for iterations in range(1, max_iterations + 1):
        order = sorted(range(len(simplex)), key=lambda index: (values[index], simplex[index]))
        simplex = [simplex[index] for index in order]
        values = [values[index] for index in order]
        best = simplex[0]
        diameter = max(distance(best, point) for point in simplex[1:])
        spread = max(abs(value - values[0]) for value in values[1:])
        if diameter <= x_tol and spread <= f_tol:
            converged = True
            break

        centroid = tuple(
            sum(simplex[row][axis] for row in range(dimension)) / dimension
            for axis in range(dimension)
        )
        worst = simplex[-1]
        reflected = tuple(
            centroid[axis] + alpha * (centroid[axis] - worst[axis])
            for axis in range(dimension)
        )
        reflected_value = _objective_value("objective", objective(reflected))
        evaluations += 1

        if values[0] <= reflected_value < values[-2]:
            simplex[-1], values[-1] = reflected, reflected_value
            continue

        if reflected_value < values[0]:
            expanded = tuple(
                centroid[axis] + gamma * (reflected[axis] - centroid[axis])
                for axis in range(dimension)
            )
            expanded_value = _objective_value("objective", objective(expanded))
            evaluations += 1
            if expanded_value < reflected_value:
                simplex[-1], values[-1] = expanded, expanded_value
            else:
                simplex[-1], values[-1] = reflected, reflected_value
            continue

        if reflected_value < values[-1]:
            contracted = tuple(
                centroid[axis] + rho * (reflected[axis] - centroid[axis])
                for axis in range(dimension)
            )
        else:
            contracted = tuple(
                centroid[axis] + rho * (worst[axis] - centroid[axis])
                for axis in range(dimension)
            )
        contracted_value = _objective_value("objective", objective(contracted))
        evaluations += 1
        if contracted_value < min(values[-1], reflected_value):
            simplex[-1], values[-1] = contracted, contracted_value
            continue

        best = simplex[0]
        for index in range(1, len(simplex)):
            simplex[index] = tuple(
                best[axis] + sigma * (simplex[index][axis] - best[axis])
                for axis in range(dimension)
            )
            values[index] = _objective_value("objective", objective(simplex[index]))
            evaluations += 1

    order = sorted(range(len(simplex)), key=lambda index: (values[index], simplex[index]))
    best_index = order[0]
    return NelderMeadReport(
        solution=simplex[best_index],
        objective=values[best_index],
        iterations=iterations,
        evaluations=evaluations,
        converged=converged,
        simplex_diameter=diameter,
        objective_spread=spread,
    )
