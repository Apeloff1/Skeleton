"""Householder and Givens orthogonal-transform reference primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_matrix, finite_scalar, finite_vector
from .linear import dot, l2_norm


@dataclass(frozen=True, slots=True)
class GivensRotation:
    cosine: float
    sine: float
    radius: float


def givens_rotation(a: Real, b: Real) -> GivensRotation:
    left = finite_scalar("a", a)
    right = finite_scalar("b", b)
    radius = math.hypot(left, right)
    if radius == 0.0:
        return GivensRotation(1.0, 0.0, 0.0)
    return GivensRotation(left / radius, right / radius, radius)


def apply_givens_pair(
    rotation: GivensRotation,
    a: Real,
    b: Real,
) -> tuple[float, float]:
    left = finite_scalar("a", a)
    right = finite_scalar("b", b)
    c = rotation.cosine
    s = rotation.sine
    return c * left + s * right, -s * left + c * right


@dataclass(frozen=True, slots=True)
class HouseholderReflection:
    vector: Vector
    beta: float
    leading_value: float


def householder_reflection(values: Sequence[Real]) -> HouseholderReflection:
    source = finite_vector("values", values)
    norm = l2_norm(source)
    if norm == 0.0:
        raise MathInvariantError(
            "Householder reflection requires a non-zero vector",
            reason="zero_norm",
            field="values",
        )
    alpha = -math.copysign(norm, source[0] if source[0] != 0.0 else 1.0)
    work = list(source)
    work[0] -= alpha
    vector_norm = l2_norm(work)
    if vector_norm == 0.0:
        raise MathInvariantError(
            "Householder reflector construction collapsed",
            reason="numerical_invariant_failure",
            field="values",
        )
    unit = tuple(value / vector_norm for value in work)
    return HouseholderReflection(vector=unit, beta=2.0, leading_value=alpha)


def apply_householder_vector(
    reflection: HouseholderReflection,
    values: Sequence[Real],
) -> Vector:
    source = finite_vector("values", values)
    if len(source) != len(reflection.vector):
        raise MathInvariantError(
            "Householder vector dimension mismatch",
            reason="dimension_mismatch",
            field="values",
        )
    coefficient = reflection.beta * dot(reflection.vector, source)
    return tuple(
        value - coefficient * direction
        for value, direction in zip(source, reflection.vector)
    )


def apply_householder_left(
    reflection: HouseholderReflection,
    matrix: Sequence[Sequence[Real]],
) -> Matrix:
    source = finite_matrix("matrix", matrix)
    if len(source) != len(reflection.vector):
        raise MathInvariantError(
            "Householder left application requires reflector length equal to row count",
            reason="dimension_mismatch",
            field="matrix",
        )
    rows = len(source)
    columns = len(source[0])
    projections = tuple(
        reflection.beta
        * sum(reflection.vector[row] * source[row][column] for row in range(rows))
        for column in range(columns)
    )
    return tuple(
        tuple(
            source[row][column] - reflection.vector[row] * projections[column]
            for column in range(columns)
        )
        for row in range(rows)
    )


def orthogonal_reflection_matrix(reflection: HouseholderReflection) -> Matrix:
    n = len(reflection.vector)
    return tuple(
        tuple(
            (1.0 if i == j else 0.0)
            - reflection.beta * reflection.vector[i] * reflection.vector[j]
            for j in range(n)
        )
        for i in range(n)
    )
