"""Generalized entropy and joint-distribution information references."""
from __future__ import annotations

import math
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, finite_matrix, finite_scalar, positive_scalar
from .numerics import compensated_sum
from .probability import entropy, normalize_distribution


def _joint_distribution(joint: Sequence[Sequence[Real]]) -> Matrix:
    matrix = finite_matrix("joint", joint)
    if any(value < 0.0 for row in matrix for value in row):
        raise MathInvariantError(
            "joint probabilities must be non-negative",
            reason="negative_probability",
            field="joint",
        )
    total = compensated_sum(value for row in matrix for value in row)
    if total <= 0.0:
        raise MathInvariantError(
            "joint distribution must have positive mass",
            reason="zero_probability_mass",
            field="joint",
        )
    return tuple(tuple(value / total for value in row) for row in matrix)


def renyi_entropy(probabilities: Sequence[Real], order: Real) -> float:
    p = normalize_distribution(probabilities)
    alpha = positive_scalar("order", order)
    if abs(alpha - 1.0) <= 1e-12:
        return entropy(p)
    power_sum = compensated_sum(value**alpha for value in p if value > 0.0)
    if power_sum <= 0.0:
        raise MathInvariantError(
            "Rényi power sum vanished",
            reason="numerical_invariant_failure",
            field="probabilities",
        )
    return math.log(power_sum) / (1.0 - alpha)


def tsallis_entropy(probabilities: Sequence[Real], order: Real) -> float:
    p = normalize_distribution(probabilities)
    q = positive_scalar("order", order)
    if abs(q - 1.0) <= 1e-12:
        return entropy(p)
    power_sum = compensated_sum(value**q for value in p if value > 0.0)
    return (1.0 - power_sum) / (q - 1.0)


def gini_impurity(probabilities: Sequence[Real]) -> float:
    p = normalize_distribution(probabilities)
    return 1.0 - compensated_sum(value * value for value in p)


def mutual_information(joint: Sequence[Sequence[Real]]) -> float:
    matrix = _joint_distribution(joint)
    rows = len(matrix)
    columns = len(matrix[0])
    row_mass = tuple(compensated_sum(matrix[i]) for i in range(rows))
    column_mass = tuple(
        compensated_sum(matrix[i][j] for i in range(rows))
        for j in range(columns)
    )
    total = 0.0
    for i in range(rows):
        for j in range(columns):
            probability = matrix[i][j]
            if probability == 0.0:
                continue
            denominator = row_mass[i] * column_mass[j]
            if denominator <= 0.0:
                raise MathInvariantError(
                    "joint support contradicts marginal support",
                    reason="invalid_probability_support",
                    field="joint",
                )
            total += probability * math.log(probability / denominator)
    if total < 0.0 and abs(total) <= 1e-14:
        return 0.0
    return finite_scalar("mutual_information", total)


def conditional_entropy_y_given_x(joint: Sequence[Sequence[Real]]) -> float:
    matrix = _joint_distribution(joint)
    row_mass = tuple(compensated_sum(row) for row in matrix)
    joint_entropy = entropy(tuple(value for row in matrix for value in row))
    return joint_entropy - entropy(row_mass)


def variation_of_information(joint: Sequence[Sequence[Real]]) -> float:
    matrix = _joint_distribution(joint)
    rows = len(matrix)
    columns = len(matrix[0])
    row_mass = tuple(compensated_sum(matrix[i]) for i in range(rows))
    column_mass = tuple(
        compensated_sum(matrix[i][j] for i in range(rows))
        for j in range(columns)
    )
    value = entropy(row_mass) + entropy(column_mass) - 2.0 * mutual_information(matrix)
    if value < 0.0 and abs(value) <= 1e-14:
        return 0.0
    return finite_scalar("variation_of_information", value)
