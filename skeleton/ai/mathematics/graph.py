"""Authority-neutral graph algebra reference primitives.

The graph runtime owns graph entities, traversal, knowledge semantics, and
promotion.  This module owns only validated matrix-level graph mathematics.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_vector, positive_scalar
from .linear import dot, matvec
from .numerics import compensated_sum


def _adjacency(
    rows: Sequence[Sequence[Real]],
    *,
    require_symmetric: bool = False,
    symmetry_tolerance: Real = 1e-12,
) -> Matrix:
    matrix = finite_matrix("adjacency", rows)
    n = len(matrix)
    if len(matrix[0]) != n:
        raise MathInvariantError(
            "adjacency must be square",
            reason="non_square_matrix",
            field="adjacency",
        )
    if any(value < 0.0 for row in matrix for value in row):
        raise MathInvariantError(
            "adjacency weights must be non-negative",
            reason="negative_graph_weight",
            field="adjacency",
        )
    if require_symmetric:
        tolerance = positive_scalar("symmetry_tolerance", symmetry_tolerance)
        scale = max(1.0, max(abs(value) for row in matrix for value in row))
        for i in range(n):
            for j in range(i + 1, n):
                if abs(matrix[i][j] - matrix[j][i]) > tolerance * scale:
                    raise MathInvariantError(
                        "undirected graph adjacency must be symmetric",
                        reason="non_symmetric_matrix",
                        field="adjacency",
                    )
    return matrix


def degree_vector(adjacency: Sequence[Sequence[Real]]) -> Vector:
    matrix = _adjacency(adjacency)
    return tuple(compensated_sum(row) for row in matrix)


def combinatorial_laplacian(
    adjacency: Sequence[Sequence[Real]],
    *,
    symmetry_tolerance: Real = 1e-12,
) -> Matrix:
    matrix = _adjacency(
        adjacency,
        require_symmetric=True,
        symmetry_tolerance=symmetry_tolerance,
    )
    degree = degree_vector(matrix)
    n = len(matrix)
    return tuple(
        tuple((degree[i] if i == j else 0.0) - matrix[i][j] for j in range(n))
        for i in range(n)
    )


def normalized_laplacian(
    adjacency: Sequence[Sequence[Real]],
    *,
    symmetry_tolerance: Real = 1e-12,
) -> Matrix:
    matrix = _adjacency(
        adjacency,
        require_symmetric=True,
        symmetry_tolerance=symmetry_tolerance,
    )
    degree = degree_vector(matrix)
    n = len(matrix)
    output: list[tuple[float, ...]] = []
    for i in range(n):
        row: list[float] = []
        for j in range(n):
            if degree[i] == 0.0 or degree[j] == 0.0:
                row.append(0.0)
            else:
                identity = 1.0 if i == j else 0.0
                row.append(identity - matrix[i][j] / math.sqrt(degree[i] * degree[j]))
        output.append(tuple(row))
    return tuple(output)


def graph_quadratic_form(
    laplacian: Sequence[Sequence[Real]],
    signal: Sequence[Real],
) -> float:
    matrix = finite_matrix("laplacian", laplacian)
    values = finite_vector("signal", signal)
    if len(matrix) != len(matrix[0]) or len(matrix) != len(values):
        raise MathInvariantError(
            "Laplacian and signal dimensions must match",
            reason="dimension_mismatch",
            field="graph_quadratic_form",
        )
    value = dot(values, matvec(matrix, values))
    if value < 0.0 and abs(value) <= 1e-12:
        return 0.0
    return value


def random_walk_matrix(
    adjacency: Sequence[Sequence[Real]],
    *,
    dangling: str = "self",
) -> Matrix:
    matrix = _adjacency(adjacency)
    if dangling not in {"self", "uniform", "error"}:
        raise MathInvariantError(
            "dangling policy must be self, uniform, or error",
            reason="invalid_dangling_policy",
            field="dangling",
        )
    n = len(matrix)
    degrees = degree_vector(matrix)
    output: list[tuple[float, ...]] = []
    for i, (row, degree) in enumerate(zip(matrix, degrees)):
        if degree > 0.0:
            output.append(tuple(value / degree for value in row))
            continue
        if dangling == "error":
            raise MathInvariantError(
                "graph contains a dangling node",
                reason="dangling_graph_node",
                field=f"adjacency[{i}]",
            )
        if dangling == "self":
            output.append(tuple(1.0 if i == j else 0.0 for j in range(n)))
        else:
            output.append(tuple(1.0 / n for _ in range(n)))
    return tuple(output)


def validate_transition_matrix(
    transition: Sequence[Sequence[Real]],
    *,
    tolerance: Real = 1e-12,
) -> Matrix:
    matrix = finite_matrix("transition", transition)
    n = len(matrix)
    if len(matrix[0]) != n:
        raise MathInvariantError(
            "transition matrix must be square",
            reason="non_square_matrix",
            field="transition",
        )
    tol = positive_scalar("tolerance", tolerance)
    for i, row in enumerate(matrix):
        if any(value < 0.0 for value in row):
            raise MathInvariantError(
                "transition probabilities must be non-negative",
                reason="negative_probability",
                field=f"transition[{i}]",
            )
        total = compensated_sum(row)
        if abs(total - 1.0) > tol:
            raise MathInvariantError(
                "transition rows must sum to one",
                reason="invalid_normalization",
                field=f"transition[{i}]",
            )
    return matrix


@dataclass(frozen=True, slots=True)
class StationaryDistributionReport:
    probabilities: Vector
    residual_l1: float
    iterations: int
    converged: bool


def stationary_distribution(
    transition: Sequence[Sequence[Real]],
    *,
    initial: Sequence[Real] | None = None,
    tolerance: Real = 1e-12,
    max_iterations: int = 10000,
) -> StationaryDistributionReport:
    matrix = validate_transition_matrix(transition, tolerance=tolerance)
    n = len(matrix)
    tol = positive_scalar("tolerance", tolerance)
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    if initial is None:
        probabilities = tuple(1.0 / n for _ in range(n))
    else:
        raw = finite_vector("initial", initial)
        if len(raw) != n or any(value < 0.0 for value in raw):
            raise MathInvariantError(
                "initial distribution is invalid",
                reason="invalid_initial_distribution",
                field="initial",
            )
        total = compensated_sum(raw)
        if total <= 0.0:
            raise MathInvariantError(
                "initial distribution must have positive mass",
                reason="zero_probability_mass",
                field="initial",
            )
        probabilities = tuple(value / total for value in raw)

    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        candidate = tuple(
            compensated_sum(probabilities[i] * matrix[i][j] for i in range(n))
            for j in range(n)
        )
        total = compensated_sum(candidate)
        if total <= 0.0:
            raise MathInvariantError(
                "stationary iteration lost probability mass",
                reason="invalid_normalization",
                field="transition",
            )
        candidate = tuple(value / total for value in candidate)
        delta = compensated_sum(abs(a - b) for a, b in zip(candidate, probabilities))
        probabilities = candidate
        if delta <= tol:
            converged = True
            break

    next_distribution = tuple(
        compensated_sum(probabilities[i] * matrix[i][j] for i in range(n))
        for j in range(n)
    )
    residual = compensated_sum(
        abs(a - b) for a, b in zip(next_distribution, probabilities)
    )
    return StationaryDistributionReport(
        probabilities=probabilities,
        residual_l1=residual,
        iterations=iterations,
        converged=converged,
    )
