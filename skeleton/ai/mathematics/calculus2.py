"""Second-order numerical calculus reference diagnostics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import l2_norm


ScalarVectorFunction = Callable[[Vector], Real]


@dataclass(frozen=True, slots=True)
class HessianReport:
    hessian: Matrix
    gradient: Vector
    symmetry_linf: float
    gradient_step: Vector
    function_evaluations: int


def finite_difference_hessian(
    function: ScalarVectorFunction,
    point: Sequence[Real],
    *,
    relative_step: Real = 1e-4,
    minimum_step: Real = 1e-6,
) -> HessianReport:
    center = finite_vector("point", point)
    rel = positive_scalar("relative_step", relative_step)
    floor = positive_scalar("minimum_step", minimum_step)
    steps = tuple(max(floor, rel * max(1.0, abs(value))) for value in center)
    evaluations = 0
    cache: dict[tuple[float, ...], float] = {}

    def evaluate(values: Vector) -> float:
        nonlocal evaluations
        if values not in cache:
            cache[values] = finite_scalar("function_value", function(values))
            evaluations += 1
        return cache[values]

    f0 = evaluate(center)
    n = len(center)
    gradient = [0.0] * n
    hessian = [[0.0] * n for _ in range(n)]

    for i in range(n):
        hi = steps[i]
        plus = list(center)
        minus = list(center)
        plus[i] += hi
        minus[i] -= hi
        fp = evaluate(tuple(plus))
        fm = evaluate(tuple(minus))
        gradient[i] = (fp - fm) / (2.0 * hi)
        hessian[i][i] = (fp - 2.0 * f0 + fm) / (hi * hi)

    for i in range(n):
        hi = steps[i]
        for j in range(i + 1, n):
            hj = steps[j]
            pp = list(center)
            pm = list(center)
            mp = list(center)
            mm = list(center)
            pp[i] += hi
            pp[j] += hj
            pm[i] += hi
            pm[j] -= hj
            mp[i] -= hi
            mp[j] += hj
            mm[i] -= hi
            mm[j] -= hj
            mixed = (
                evaluate(tuple(pp))
                - evaluate(tuple(pm))
                - evaluate(tuple(mp))
                + evaluate(tuple(mm))
            ) / (4.0 * hi * hj)
            hessian[i][j] = mixed
            hessian[j][i] = mixed

    matrix = tuple(tuple(finite_scalar("hessian", value) for value in row) for row in hessian)
    gradient_vector = finite_vector("gradient", gradient)
    symmetry = max(
        abs(matrix[i][j] - matrix[j][i])
        for i in range(n)
        for j in range(n)
    )
    return HessianReport(
        hessian=matrix,
        gradient=gradient_vector,
        symmetry_linf=symmetry,
        gradient_step=steps,
        function_evaluations=evaluations,
    )


def hessian_vector_product(
    hessian: Sequence[Sequence[Real]],
    vector: Sequence[Real],
) -> Vector:
    matrix = tuple(finite_vector(f"hessian[{index}]", row) for index, row in enumerate(hessian))
    direction = finite_vector("vector", vector)
    if not matrix or len(matrix) != len(matrix[0]) or len(matrix) != len(direction):
        raise MathInvariantError(
            "Hessian/vector dimensions must match",
            reason="dimension_mismatch",
            field="hessian_vector_product",
        )
    return tuple(
        sum(row[column] * direction[column] for column in range(len(direction)))
        for row in matrix
    )


def quadratic_model_change(
    gradient: Sequence[Real],
    hessian: Sequence[Sequence[Real]],
    step: Sequence[Real],
) -> float:
    g = finite_vector("gradient", gradient)
    s = finite_vector("step", step)
    if len(g) != len(s):
        raise MathInvariantError(
            "gradient and step dimensions must match",
            reason="dimension_mismatch",
            field="quadratic_model",
        )
    hv = hessian_vector_product(hessian, s)
    linear = sum(a * b for a, b in zip(g, s))
    quadratic = 0.5 * sum(a * b for a, b in zip(s, hv))
    return finite_scalar("quadratic_model_change", linear + quadratic)


def gradient_norm(report: HessianReport) -> float:
    return l2_norm(report.gradient)
