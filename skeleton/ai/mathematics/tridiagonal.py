"""Tridiagonal matrix products and Thomas solves with residual evidence."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector, positive_scalar


def _bands(
    lower: Sequence[Real],
    diagonal: Sequence[Real],
    upper: Sequence[Real],
) -> tuple[Vector, Vector, Vector]:
    d = finite_vector("diagonal", diagonal)
    l = finite_vector("lower", lower) if lower else ()
    u = finite_vector("upper", upper) if upper else ()
    n = len(d)
    if len(l) != max(0, n - 1) or len(u) != max(0, n - 1):
        raise MathInvariantError(
            "tridiagonal bands have inconsistent lengths",
            reason="dimension_mismatch",
            field="bands",
        )
    return l, d, u


def tridiagonal_matvec(
    lower: Sequence[Real],
    diagonal: Sequence[Real],
    upper: Sequence[Real],
    vector: Sequence[Real],
) -> Vector:
    l, d, u = _bands(lower, diagonal, upper)
    x = finite_vector("vector", vector)
    if len(x) != len(d):
        raise MathInvariantError(
            "tridiagonal matvec dimension mismatch",
            reason="dimension_mismatch",
            field="vector",
        )
    result = []
    for i in range(len(d)):
        value = d[i] * x[i]
        if i:
            value += l[i - 1] * x[i - 1]
        if i + 1 < len(d):
            value += u[i] * x[i + 1]
        result.append(value)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class TridiagonalSolveReport:
    solution: Vector
    residual_linf: float
    minimum_effective_pivot: float


def solve_tridiagonal(
    lower: Sequence[Real],
    diagonal: Sequence[Real],
    upper: Sequence[Real],
    rhs: Sequence[Real],
    *,
    pivot_tolerance: Real = 1e-14,
) -> TridiagonalSolveReport:
    l, d, u = _bands(lower, diagonal, upper)
    b = finite_vector("rhs", rhs)
    n = len(d)
    if len(b) != n:
        raise MathInvariantError(
            "tridiagonal rhs dimension mismatch",
            reason="dimension_mismatch",
            field="rhs",
        )
    tolerance = positive_scalar("pivot_tolerance", pivot_tolerance)
    scale = max(1.0, max(abs(value) for value in d))
    effective = list(d)
    transformed_rhs = list(b)
    minimum_pivot = math.inf

    for i in range(1, n):
        pivot = effective[i - 1]
        minimum_pivot = min(minimum_pivot, abs(pivot))
        if abs(pivot) <= tolerance * scale:
            raise MathInvariantError(
                "tridiagonal system has a zero or tiny effective pivot",
                reason="singular_matrix",
                field=f"diagonal[{i - 1}]",
            )
        multiplier = l[i - 1] / pivot
        effective[i] -= multiplier * u[i - 1]
        transformed_rhs[i] -= multiplier * transformed_rhs[i - 1]
    minimum_pivot = min(minimum_pivot, abs(effective[-1]))
    if abs(effective[-1]) <= tolerance * scale:
        raise MathInvariantError(
            "tridiagonal system has a zero or tiny final pivot",
            reason="singular_matrix",
            field=f"diagonal[{n - 1}]",
        )

    solution = [0.0] * n
    solution[-1] = transformed_rhs[-1] / effective[-1]
    for i in range(n - 2, -1, -1):
        solution[i] = (transformed_rhs[i] - u[i] * solution[i + 1]) / effective[i]
    result = finite_vector("solution", solution)
    residual_vector = tridiagonal_matvec(l, d, u, result)
    residual = max(abs(a - b) for a, b in zip(residual_vector, b))
    return TridiagonalSolveReport(
        solution=result,
        residual_linf=residual,
        minimum_effective_pivot=minimum_pivot,
    )
