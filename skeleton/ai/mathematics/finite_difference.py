"""Finite-difference derivatives and one-dimensional Poisson references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector, positive_scalar


def first_derivative_grid(values: Sequence[Real], spacing: Real) -> Vector:
    source = finite_vector("values", values)
    h = positive_scalar("spacing", spacing)
    if len(source) < 3:
        raise MathInvariantError(
            "second-order first derivative requires at least three points",
            reason="insufficient_observations",
            field="values",
        )
    output = [0.0] * len(source)
    output[0] = (-3.0 * source[0] + 4.0 * source[1] - source[2]) / (2.0 * h)
    output[-1] = (3.0 * source[-1] - 4.0 * source[-2] + source[-3]) / (2.0 * h)
    for index in range(1, len(source) - 1):
        output[index] = (source[index + 1] - source[index - 1]) / (2.0 * h)
    return tuple(finite_scalar("derivative", value) for value in output)


def second_derivative_grid(values: Sequence[Real], spacing: Real) -> Vector:
    source = finite_vector("values", values)
    h = positive_scalar("spacing", spacing)
    if len(source) < 4:
        raise MathInvariantError(
            "second-order boundary Laplacian requires at least four points",
            reason="insufficient_observations",
            field="values",
        )
    scale = h * h
    output = [0.0] * len(source)
    output[0] = (2.0 * source[0] - 5.0 * source[1] + 4.0 * source[2] - source[3]) / scale
    output[-1] = (2.0 * source[-1] - 5.0 * source[-2] + 4.0 * source[-3] - source[-4]) / scale
    for index in range(1, len(source) - 1):
        output[index] = (source[index - 1] - 2.0 * source[index] + source[index + 1]) / scale
    return tuple(finite_scalar("second_derivative", value) for value in output)


@dataclass(frozen=True, slots=True)
class Poisson1DReport:
    solution: Vector
    residual_linf: float
    spacing: float
    interior_points: int


def solve_poisson_dirichlet_1d(
    source: Sequence[Real],
    spacing: Real,
    *,
    left_boundary: Real = 0.0,
    right_boundary: Real = 0.0,
) -> Poisson1DReport:
    rhs_source = finite_vector("source", source)
    h = positive_scalar("spacing", spacing)
    left = finite_scalar("left_boundary", left_boundary)
    right = finite_scalar("right_boundary", right_boundary)
    n = len(rhs_source)
    diagonal = [2.0] * n
    upper = [-1.0] * max(0, n - 1)
    lower = [-1.0] * max(0, n - 1)
    rhs = [h * h * value for value in rhs_source]
    rhs[0] += left
    rhs[-1] += right

    for index in range(1, n):
        multiplier = lower[index - 1] / diagonal[index - 1]
        diagonal[index] -= multiplier * upper[index - 1]
        rhs[index] -= multiplier * rhs[index - 1]
    interior = [0.0] * n
    interior[-1] = rhs[-1] / diagonal[-1]
    for index in range(n - 2, -1, -1):
        interior[index] = (rhs[index] - upper[index] * interior[index + 1]) / diagonal[index]

    full = (left, *interior, right)
    residual = 0.0
    for index, forcing in enumerate(rhs_source, start=1):
        discrete = (2.0 * full[index] - full[index - 1] - full[index + 1]) / (h * h)
        residual = max(residual, abs(discrete - forcing))
    return Poisson1DReport(
        solution=tuple(full),
        residual_linf=residual,
        spacing=h,
        interior_points=n,
    )


def explicit_diffusion_stable_step(
    spacing: Real,
    diffusivity: Real,
    *,
    dimensions: int = 1,
) -> float:
    h = positive_scalar("spacing", spacing)
    coefficient = positive_scalar("diffusivity", diffusivity)
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions < 1:
        raise MathInvariantError(
            "dimensions must be a positive integer",
            reason="invalid_dimension",
            field="dimensions",
        )
    return h * h / (2.0 * dimensions * coefficient)
