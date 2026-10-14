"""Deterministic constrained optimization reference routines."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import dot, l2_norm

Objective = Callable[[Vector], Real]
Bound = tuple[Real | None, Real | None]


@dataclass(frozen=True, slots=True)
class OptimizationConfig:
    max_iterations: int = 200
    gradient_tolerance: float = 1e-8
    initial_step: float = 1.0
    armijo: float = 1e-4
    backtrack: float = 0.5
    minimum_step: float = 1e-12
    relative_difference_step: float = 1e-6

    def __post_init__(self) -> None:
        if isinstance(self.max_iterations, bool) or self.max_iterations < 1:
            raise MathInvariantError(
                "max_iterations must be a positive integer",
                reason="invalid_optimization_config",
                field="max_iterations",
            )
        positive_scalar("gradient_tolerance", self.gradient_tolerance)
        positive_scalar("initial_step", self.initial_step)
        armijo = positive_scalar("armijo", self.armijo)
        backtrack = positive_scalar("backtrack", self.backtrack)
        positive_scalar("minimum_step", self.minimum_step)
        positive_scalar("relative_difference_step", self.relative_difference_step)
        if armijo >= 1.0 or backtrack >= 1.0:
            raise MathInvariantError(
                "armijo and backtrack must be in (0, 1)",
                reason="invalid_optimization_config",
                field="line_search",
            )


@dataclass(frozen=True, slots=True)
class OptimizationStep:
    iteration: int
    objective: float
    gradient_norm: float
    step_size: float


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    point: Vector
    objective: float
    converged: bool
    reason: str
    iterations: int
    trace: tuple[OptimizationStep, ...]


def _objective_value(objective: Objective, point: Vector) -> float:
    try:
        raw = objective(point)
    except Exception:
        raise
    return finite_scalar("objective", raw)


def _normalize_bounds(bounds: Sequence[Bound] | None, dimensions: int) -> tuple[tuple[float | None, float | None], ...]:
    if bounds is None:
        return tuple((None, None) for _ in range(dimensions))
    if len(bounds) != dimensions:
        raise MathInvariantError(
            "bounds dimension mismatch",
            reason="dimension_mismatch",
            field="bounds",
        )
    normalized: list[tuple[float | None, float | None]] = []
    for index, pair in enumerate(bounds):
        if len(pair) != 2:
            raise MathInvariantError(
                "each bound must be a (lower, upper) pair",
                reason="invalid_bound",
                field=f"bounds[{index}]",
            )
        raw_lower, raw_upper = pair
        lower = None if raw_lower is None else finite_scalar(f"bounds[{index}].lower", raw_lower)
        upper = None if raw_upper is None else finite_scalar(f"bounds[{index}].upper", raw_upper)
        if lower is not None and upper is not None and lower > upper:
            raise MathInvariantError(
                "lower bound exceeds upper bound",
                reason="invalid_bound",
                field=f"bounds[{index}]",
            )
        normalized.append((lower, upper))
    return tuple(normalized)


def project(point: Sequence[Real], bounds: Sequence[Bound] | None = None) -> Vector:
    values = finite_vector("point", point)
    actual_bounds = _normalize_bounds(bounds, len(values))
    output: list[float] = []
    for value, (lower, upper) in zip(values, actual_bounds):
        if lower is not None:
            value = max(value, lower)
        if upper is not None:
            value = min(value, upper)
        output.append(value)
    return tuple(output)


def finite_difference_gradient(
    objective: Objective,
    point: Sequence[Real],
    *,
    bounds: Sequence[Bound] | None = None,
    relative_step: Real = 1e-6,
) -> Vector:
    x = finite_vector("point", point)
    actual_bounds = _normalize_bounds(bounds, len(x))
    relative = positive_scalar("relative_step", relative_step)
    base = _objective_value(objective, x)
    gradient: list[float] = []
    for index, value in enumerate(x):
        lower, upper = actual_bounds[index]
        h = relative * max(1.0, abs(value))
        plus_available = upper is None or value + h <= upper
        minus_available = lower is None or value - h >= lower
        if not plus_available and not minus_available:
            gradient.append(0.0)
            continue
        if plus_available and minus_available:
            plus = list(x)
            minus = list(x)
            plus[index] += h
            minus[index] -= h
            numerator = _objective_value(objective, tuple(plus)) - _objective_value(objective, tuple(minus))
            derivative = numerator / (2.0 * h)
        elif plus_available:
            plus = list(x)
            plus[index] += h
            derivative = (_objective_value(objective, tuple(plus)) - base) / h
        else:
            minus = list(x)
            minus[index] -= h
            derivative = (base - _objective_value(objective, tuple(minus))) / h
        gradient.append(finite_scalar(f"gradient[{index}]", derivative))
    return tuple(gradient)


def projected_gradient_descent(
    objective: Objective,
    initial: Sequence[Real],
    *,
    bounds: Sequence[Bound] | None = None,
    config: OptimizationConfig | None = None,
) -> OptimizationResult:
    actual = config or OptimizationConfig()
    initial_vector = finite_vector("initial", initial)
    actual_bounds = _normalize_bounds(bounds, len(initial_vector))
    x = project(initial_vector, actual_bounds)
    value = _objective_value(objective, x)
    trace: list[OptimizationStep] = []

    for iteration in range(actual.max_iterations):
        gradient = finite_difference_gradient(
            objective,
            x,
            bounds=actual_bounds,
            relative_step=actual.relative_difference_step,
        )
        gradient_norm = l2_norm(gradient)
        if gradient_norm <= actual.gradient_tolerance:
            return OptimizationResult(
                point=x,
                objective=value,
                converged=True,
                reason="gradient_tolerance",
                iterations=iteration,
                trace=tuple(trace),
            )

        step = actual.initial_step
        accepted = False
        candidate = x
        candidate_value = value
        while step >= actual.minimum_step:
            candidate = project(
                tuple(current - step * derivative for current, derivative in zip(x, gradient)),
                actual_bounds,
            )
            direction = tuple(new - current for new, current in zip(candidate, x))
            if all(delta == 0.0 for delta in direction):
                return OptimizationResult(
                    point=x,
                    objective=value,
                    converged=True,
                    reason="projected_stationary",
                    iterations=iteration,
                    trace=tuple(trace),
                )
            candidate_value = _objective_value(objective, candidate)
            sufficient_decrease = value + actual.armijo * dot(gradient, direction)
            if candidate_value <= sufficient_decrease:
                accepted = True
                break
            step *= actual.backtrack

        trace.append(
            OptimizationStep(
                iteration=iteration,
                objective=value,
                gradient_norm=gradient_norm,
                step_size=step if accepted else 0.0,
            )
        )
        if not accepted:
            return OptimizationResult(
                point=x,
                objective=value,
                converged=False,
                reason="line_search_exhausted",
                iterations=iteration + 1,
                trace=tuple(trace),
            )

        x = candidate
        value = candidate_value

    return OptimizationResult(
        point=x,
        objective=value,
        converged=False,
        reason="iteration_limit",
        iterations=actual.max_iterations,
        trace=tuple(trace),
    )
