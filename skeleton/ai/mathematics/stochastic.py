"""Finite-state stochastic-process reference analysis."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_vector
from .graph import validate_transition_matrix
from .linear import matmul, solve_linear_system
from .numerics import compensated_sum
from .probability import normalize_distribution


def propagate_distribution(
    distribution: Sequence[Real],
    transition: Sequence[Sequence[Real]],
    *,
    steps: int = 1,
) -> Vector:
    matrix = validate_transition_matrix(transition)
    probabilities = normalize_distribution(distribution)
    n = len(matrix)
    if len(probabilities) != n:
        raise MathInvariantError(
            "distribution dimension must match transition matrix",
            reason="dimension_mismatch",
            field="distribution",
        )
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 0:
        raise MathInvariantError(
            "steps must be a non-negative integer",
            reason="invalid_iteration_limit",
            field="steps",
        )
    current = probabilities
    for _ in range(steps):
        current = tuple(
            compensated_sum(current[i] * matrix[i][j] for i in range(n))
            for j in range(n)
        )
        current = normalize_distribution(current)
    return current


def transition_power(
    transition: Sequence[Sequence[Real]],
    exponent: int,
) -> Matrix:
    matrix = validate_transition_matrix(transition)
    if isinstance(exponent, bool) or not isinstance(exponent, int) or exponent < 0:
        raise MathInvariantError(
            "transition exponent must be a non-negative integer",
            reason="invalid_exponent",
            field="exponent",
        )
    n = len(matrix)
    result: Matrix = tuple(
        tuple(1.0 if i == j else 0.0 for j in range(n))
        for i in range(n)
    )
    base = matrix
    power = exponent
    while power:
        if power & 1:
            result = matmul(result, base)
        power >>= 1
        if power:
            base = matmul(base, base)
    return result


@dataclass(frozen=True, slots=True)
class HittingTimeReport:
    target_states: tuple[int, ...]
    expected_steps: Vector
    residual_linf: float


def expected_hitting_times(
    transition: Sequence[Sequence[Real]],
    targets: Sequence[int],
) -> HittingTimeReport:
    matrix = validate_transition_matrix(transition)
    n = len(matrix)
    target_set = set()
    for target in targets:
        if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < n:
            raise MathInvariantError(
                "target state is out of range",
                reason="invalid_state",
                field="targets",
            )
        target_set.add(target)
    if not target_set:
        raise MathInvariantError(
            "at least one target state is required",
            reason="empty_target_set",
            field="targets",
        )
    transient = [state for state in range(n) if state not in target_set]
    expected = [0.0] * n
    if transient:
        system = []
        rhs = []
        for state in transient:
            row = []
            for other in transient:
                row.append((1.0 if state == other else 0.0) - matrix[state][other])
            system.append(tuple(row))
            rhs.append(1.0)
        try:
            solution = solve_linear_system(tuple(system), tuple(rhs)).solution
        except MathInvariantError as exc:
            raise MathInvariantError(
                "target set is not reached with finite expected time from every transient state",
                reason="infinite_hitting_time",
                field="targets",
            ) from exc
        for state, value in zip(transient, solution):
            if value < -1e-10:
                raise MathInvariantError(
                    "hitting-time solve produced negative expectation",
                    reason="numerical_invariant_failure",
                    field="expected_steps",
                )
            expected[state] = max(0.0, value)

    residual = 0.0
    for state in transient:
        right = 1.0 + compensated_sum(
            matrix[state][other] * expected[other]
            for other in transient
        )
        residual = max(residual, abs(expected[state] - right))
    return HittingTimeReport(
        target_states=tuple(sorted(target_set)),
        expected_steps=tuple(expected),
        residual_linf=residual,
    )


def absorbing_probability(
    transition: Sequence[Sequence[Real]],
    target: int,
    *,
    absorbing_states: Sequence[int],
) -> Vector:
    matrix = validate_transition_matrix(transition)
    n = len(matrix)
    if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < n:
        raise MathInvariantError(
            "target state is out of range",
            reason="invalid_state",
            field="target",
        )
    absorbing = set(absorbing_states)
    if target not in absorbing:
        raise MathInvariantError(
            "target must be one of the absorbing states",
            reason="invalid_target_state",
            field="target",
        )
    for state in absorbing:
        if isinstance(state, bool) or not isinstance(state, int) or not 0 <= state < n:
            raise MathInvariantError(
                "absorbing state is out of range",
                reason="invalid_state",
                field="absorbing_states",
            )
        for column, probability in enumerate(matrix[state]):
            expected = 1.0 if column == state else 0.0
            if abs(probability - expected) > 1e-12:
                raise MathInvariantError(
                    "declared absorbing state does not have an absorbing transition row",
                    reason="non_absorbing_state",
                    field=f"absorbing_states[{state}]",
                )
    transient = [state for state in range(n) if state not in absorbing]
    probabilities = [1.0 if state == target else 0.0 for state in range(n)]
    if transient:
        system = []
        rhs = []
        for state in transient:
            system.append(tuple(
                (1.0 if state == other else 0.0) - matrix[state][other]
                for other in transient
            ))
            rhs.append(matrix[state][target])
        solution = solve_linear_system(tuple(system), tuple(rhs)).solution
        for state, value in zip(transient, solution):
            probabilities[state] = max(0.0, min(1.0, value))
    return tuple(probabilities)
