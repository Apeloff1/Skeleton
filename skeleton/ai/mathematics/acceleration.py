"""Fixed-point iteration and regularized Anderson acceleration references."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import l2_norm, solve_linear_system
from .numerics import compensated_sum


FixedPointMap = Callable[[Vector], Sequence[Real]]


def _map_value(function: FixedPointMap, point: Vector) -> Vector:
    value = finite_vector("fixed_point_map", function(point))
    if len(value) != len(point):
        raise MathInvariantError(
            "fixed-point map changed vector dimension",
            reason="dimension_mismatch",
            field="fixed_point_map",
        )
    return value


@dataclass(frozen=True, slots=True)
class FixedPointReport:
    solution: Vector
    residual_l2: float
    iterations: int
    evaluations: int
    converged: bool
    method: str
    history_size: int


def fixed_point_iteration(
    function: FixedPointMap,
    initial: Sequence[Real],
    *,
    tolerance: Real = 1e-10,
    max_iterations: int = 10000,
    relaxation: Real = 1.0,
) -> FixedPointReport:
    current = finite_vector("initial", initial)
    tol = positive_scalar("tolerance", tolerance)
    omega = positive_scalar("relaxation", relaxation)
    if omega > 1.0:
        raise MathInvariantError(
            "reference fixed-point relaxation must lie in (0, 1]",
            reason="invalid_relaxation",
            field="relaxation",
        )
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    evaluations = 0
    residual_norm = float("inf")
    for iteration in range(1, max_iterations + 1):
        mapped = _map_value(function, current)
        evaluations += 1
        residual = tuple(mapped[i] - current[i] for i in range(len(current)))
        residual_norm = l2_norm(residual)
        if residual_norm <= tol:
            return FixedPointReport(mapped, residual_norm, iteration, evaluations, True, "fixed_point", 1)
        current = tuple(current[i] + omega * residual[i] for i in range(len(current)))
    return FixedPointReport(current, residual_norm, max_iterations, evaluations, False, "fixed_point", 1)


def anderson_accelerate(
    function: FixedPointMap,
    initial: Sequence[Real],
    *,
    memory: int = 5,
    tolerance: Real = 1e-10,
    regularization: Real = 1e-12,
    max_iterations: int = 1000,
) -> FixedPointReport:
    current = finite_vector("initial", initial)
    tol = positive_scalar("tolerance", tolerance)
    reg = positive_scalar("regularization", regularization)
    if isinstance(memory, bool) or not isinstance(memory, int) or memory < 1:
        raise MathInvariantError(
            "Anderson memory must be a positive integer",
            reason="invalid_memory",
            field="memory",
        )
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    mapped_history: list[Vector] = []
    residual_history: list[Vector] = []
    evaluations = 0
    residual_norm = float("inf")

    for iteration in range(1, max_iterations + 1):
        mapped = _map_value(function, current)
        evaluations += 1
        residual = tuple(mapped[i] - current[i] for i in range(len(current)))
        residual_norm = l2_norm(residual)
        if residual_norm <= tol:
            return FixedPointReport(
                mapped,
                residual_norm,
                iteration,
                evaluations,
                True,
                "anderson",
                len(residual_history) + 1,
            )

        mapped_history.append(mapped)
        residual_history.append(residual)
        if len(mapped_history) > memory:
            mapped_history.pop(0)
            residual_history.pop(0)

        count = len(residual_history)
        if count == 1:
            current = mapped
            continue

        gram = tuple(
            tuple(
                compensated_sum(
                    residual_history[i][k] * residual_history[j][k]
                    for k in range(len(current))
                ) + (reg if i == j else 0.0)
                for j in range(count)
            ) + (1.0,)
            for i in range(count)
        ) + (tuple(1.0 for _ in range(count)) + (0.0,),)
        rhs = tuple(0.0 for _ in range(count)) + (1.0,)
        try:
            coefficients = solve_linear_system(gram, rhs).solution[:count]
            current = tuple(
                compensated_sum(coefficients[i] * mapped_history[i][axis] for i in range(count))
                for axis in range(len(current))
            )
        except MathInvariantError:
            current = mapped

    return FixedPointReport(
        current,
        residual_norm,
        max_iterations,
        evaluations,
        False,
        "anderson",
        len(residual_history),
    )
