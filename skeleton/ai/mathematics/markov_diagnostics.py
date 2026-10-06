"""Finite Markov-chain reversibility and mixing diagnostics."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_vector, positive_scalar
from .graph import stationary_distribution, validate_transition_matrix
from .numerics import compensated_sum


def total_variation_distance(
    left: Sequence[Real],
    right: Sequence[Real],
) -> float:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    if len(a) != len(b):
        raise MathInvariantError(
            "total-variation distributions must share dimension",
            reason="dimension_mismatch",
            field="distributions",
        )
    if any(value < 0.0 for value in a + b):
        raise MathInvariantError(
            "total-variation distributions must be non-negative",
            reason="negative_probability",
            field="distributions",
        )
    total_a = compensated_sum(a)
    total_b = compensated_sum(b)
    if total_a <= 0.0 or total_b <= 0.0:
        raise MathInvariantError(
            "total-variation distributions require positive mass",
            reason="zero_probability_mass",
            field="distributions",
        )
    pa = tuple(value / total_a for value in a)
    pb = tuple(value / total_b for value in b)
    return 0.5 * compensated_sum(abs(x - y) for x, y in zip(pa, pb))


def dobrushin_coefficient(transition: Sequence[Sequence[Real]]) -> float:
    matrix = validate_transition_matrix(transition)
    n = len(matrix)
    maximum = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            maximum = max(
                maximum,
                0.5 * compensated_sum(abs(a - b) for a, b in zip(matrix[i], matrix[j])),
            )
    return maximum


@dataclass(frozen=True, slots=True)
class DetailedBalanceReport:
    stationary: Vector
    maximum_flux_residual: float
    l1_flux_residual: float
    reversible: bool


def detailed_balance_report(
    transition: Sequence[Sequence[Real]],
    *,
    stationary: Sequence[Real] | None = None,
    tolerance: Real = 1e-12,
) -> DetailedBalanceReport:
    matrix = validate_transition_matrix(transition, tolerance=tolerance)
    tol = positive_scalar("tolerance", tolerance)
    if stationary is None:
        report = stationary_distribution(matrix, tolerance=tol)
        if not report.converged:
            raise MathInvariantError(
                "stationary distribution did not converge for detailed-balance check",
                reason="stationary_non_convergence",
                field="transition",
            )
        probabilities = report.probabilities
    else:
        raw = finite_vector("stationary", stationary)
        if len(raw) != len(matrix) or any(value < 0.0 for value in raw):
            raise MathInvariantError(
                "stationary candidate is invalid",
                reason="invalid_initial_distribution",
                field="stationary",
            )
        total = compensated_sum(raw)
        probabilities = tuple(value / total for value in raw)
    residuals = []
    for i in range(len(matrix)):
        for j in range(i + 1, len(matrix)):
            residuals.append(abs(probabilities[i] * matrix[i][j] - probabilities[j] * matrix[j][i]))
    maximum = max(residuals, default=0.0)
    l1 = compensated_sum(residuals)
    return DetailedBalanceReport(probabilities, maximum, l1, maximum <= tol)


@dataclass(frozen=True, slots=True)
class MixingReport:
    stationary: Vector
    distances: Vector
    tolerance: float
    mixing_step: int | None
    contraction_coefficient: float


def mixing_profile(
    transition: Sequence[Sequence[Real]],
    initial: Sequence[Real],
    *,
    steps: int,
    tolerance: Real = 1e-6,
) -> MixingReport:
    matrix = validate_transition_matrix(transition)
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
        raise MathInvariantError(
            "mixing profile steps must be a non-negative integer",
            reason="invalid_iteration_limit",
            field="steps",
        )
    tol = positive_scalar("tolerance", tolerance)
    stationary = stationary_distribution(matrix, tolerance=min(tol * 1e-3, 1e-12))
    if not stationary.converged:
        raise MathInvariantError(
            "stationary distribution did not converge",
            reason="stationary_non_convergence",
            field="transition",
        )
    state = finite_vector("initial", initial)
    if len(state) != len(matrix) or any(value < 0.0 for value in state):
        raise MathInvariantError(
            "mixing initial distribution is invalid",
            reason="invalid_initial_distribution",
            field="initial",
        )
    mass = compensated_sum(state)
    if mass <= 0.0:
        raise MathInvariantError(
            "mixing initial distribution requires positive mass",
            reason="zero_probability_mass",
            field="initial",
        )
    state = tuple(value / mass for value in state)
    distances = [total_variation_distance(state, stationary.probabilities)]
    mixing_step = 0 if distances[0] <= tol else None

    for step in range(1, steps + 1):
        state = tuple(
            compensated_sum(state[i] * matrix[i][j] for i in range(len(matrix)))
            for j in range(len(matrix))
        )
        distance = total_variation_distance(state, stationary.probabilities)
        distances.append(distance)
        if mixing_step is None and distance <= tol:
            mixing_step = step
    return MixingReport(
        stationary=stationary.probabilities,
        distances=tuple(distances),
        tolerance=tol,
        mixing_step=mixing_step,
        contraction_coefficient=dobrushin_coefficient(matrix),
    )
