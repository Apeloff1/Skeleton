"""Optimal-transport distance and entropy-regularized transport references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_scalar, finite_vector, positive_scalar
from .numerics import compensated_sum
from .probability import normalize_distribution


def wasserstein_distance_1d(
    left_positions: Sequence[Real],
    right_positions: Sequence[Real],
    *,
    left_weights: Sequence[Real] | None = None,
    right_weights: Sequence[Real] | None = None,
    order: Real = 1.0,
) -> float:
    left = finite_vector("left_positions", left_positions)
    right = finite_vector("right_positions", right_positions)
    p = positive_scalar("order", order)
    if p < 1.0:
        raise MathInvariantError(
            "Wasserstein order must be >= 1",
            reason="invalid_transport_order",
            field="order",
        )
    lw = normalize_distribution(
        tuple(1.0 for _ in left) if left_weights is None else left_weights
    )
    rw = normalize_distribution(
        tuple(1.0 for _ in right) if right_weights is None else right_weights
    )
    if len(lw) != len(left) or len(rw) != len(right):
        raise MathInvariantError(
            "transport positions and weights must align",
            reason="dimension_mismatch",
            field="weights",
        )
    litems = sorted(zip(left, lw), key=lambda item: item[0])
    ritems = sorted(zip(right, rw), key=lambda item: item[0])
    i = j = 0
    lremaining = litems[0][1]
    rremaining = ritems[0][1]
    cost = 0.0
    while i < len(litems) and j < len(ritems):
        moved = min(lremaining, rremaining)
        cost += moved * abs(litems[i][0] - ritems[j][0]) ** p
        lremaining -= moved
        rremaining -= moved
        if lremaining <= 1e-15:
            i += 1
            if i < len(litems):
                lremaining = litems[i][1]
        if rremaining <= 1e-15:
            j += 1
            if j < len(ritems):
                rremaining = ritems[j][1]
    return finite_scalar("wasserstein_distance", cost ** (1.0 / p))


@dataclass(frozen=True, slots=True)
class SinkhornReport:
    plan: Matrix
    transport_cost: float
    iterations: int
    converged: bool
    marginal_residual_linf: float
    regularization: float


def sinkhorn_transport(
    costs: Sequence[Sequence[Real]],
    source_weights: Sequence[Real],
    target_weights: Sequence[Real],
    *,
    regularization: Real = 0.1,
    tolerance: Real = 1e-9,
    max_iterations: int = 10000,
) -> SinkhornReport:
    cost = finite_matrix("costs", costs)
    rows = len(cost)
    columns = len(cost[0])
    if any(value < 0.0 for row in cost for value in row):
        raise MathInvariantError(
            "transport costs must be non-negative",
            reason="negative_transport_cost",
            field="costs",
        )
    source = normalize_distribution(source_weights)
    target = normalize_distribution(target_weights)
    if len(source) != rows or len(target) != columns:
        raise MathInvariantError(
            "transport marginals must match cost-matrix dimensions",
            reason="dimension_mismatch",
            field="weights",
        )
    epsilon = positive_scalar("regularization", regularization)
    tol = positive_scalar("tolerance", tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )

    kernel = tuple(
        tuple(math.exp(-value / epsilon) for value in row)
        for row in cost
    )
    if any(all(value == 0.0 for value in row) for row in kernel):
        raise MathInvariantError(
            "transport kernel underflow removed an entire source row",
            reason="kernel_underflow",
            field="regularization",
        )
    for column in range(columns):
        if all(kernel[row][column] == 0.0 for row in range(rows)):
            raise MathInvariantError(
                "transport kernel underflow removed an entire target column",
                reason="kernel_underflow",
                field="regularization",
            )

    u = [1.0] * rows
    v = [1.0] * columns
    converged = False
    iterations = 0
    residual = math.inf

    for iterations in range(1, max_iterations + 1):
        for i in range(rows):
            denominator = compensated_sum(kernel[i][j] * v[j] for j in range(columns))
            if denominator <= 0.0:
                raise MathInvariantError(
                    "Sinkhorn source scaling lost support",
                    reason="zero_transport_support",
                    field=f"source[{i}]",
                )
            u[i] = source[i] / denominator
        for j in range(columns):
            denominator = compensated_sum(kernel[i][j] * u[i] for i in range(rows))
            if denominator <= 0.0:
                raise MathInvariantError(
                    "Sinkhorn target scaling lost support",
                    reason="zero_transport_support",
                    field=f"target[{j}]",
                )
            v[j] = target[j] / denominator
        if any(not math.isfinite(value) for value in u + v):
            raise MathInvariantError(
                "Sinkhorn scaling became non-finite",
                reason="non_finite_result",
                field="scaling",
            )

        if iterations == 1 or iterations % 10 == 0:
            plan = tuple(
                tuple(u[i] * kernel[i][j] * v[j] for j in range(columns))
                for i in range(rows)
            )
            row_residual = max(
                abs(compensated_sum(plan[i]) - source[i])
                for i in range(rows)
            )
            column_residual = max(
                abs(compensated_sum(plan[i][j] for i in range(rows)) - target[j])
                for j in range(columns)
            )
            residual = max(row_residual, column_residual)
            if residual <= tol:
                converged = True
                break

    plan = tuple(
        tuple(u[i] * kernel[i][j] * v[j] for j in range(columns))
        for i in range(rows)
    )
    row_residual = max(
        abs(compensated_sum(plan[i]) - source[i])
        for i in range(rows)
    )
    column_residual = max(
        abs(compensated_sum(plan[i][j] for i in range(rows)) - target[j])
        for j in range(columns)
    )
    residual = max(row_residual, column_residual)
    transport_cost = compensated_sum(
        plan[i][j] * cost[i][j]
        for i in range(rows)
        for j in range(columns)
    )
    return SinkhornReport(
        plan=plan,
        transport_cost=finite_scalar("transport_cost", transport_cost),
        iterations=iterations,
        converged=converged,
        marginal_residual_linf=residual,
        regularization=epsilon,
    )
