"""Numerical differentiation and derivative-consistency reference checks."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable, Sequence

from .contracts import MathInvariantError, Matrix, Vector, finite_scalar, finite_vector, positive_scalar
from .linear import l2_norm


ScalarFunction = Callable[[float], Real]
VectorFunction = Callable[[Vector], Sequence[Real]]
ScalarVectorFunction = Callable[[Vector], Real]


@dataclass(frozen=True, slots=True)
class DerivativeReport:
    derivative: float
    coarse_estimate: float
    fine_estimate: float
    richardson_error_estimate: float
    step: float
    evaluations: int


def richardson_derivative(
    function: ScalarFunction,
    x: Real,
    *,
    step: Real = 1e-3,
) -> DerivativeReport:
    point = finite_scalar("x", x)
    h = positive_scalar("step", step)

    def evaluate(value: float) -> float:
        return finite_scalar("function_value", function(value))

    coarse = (evaluate(point + h) - evaluate(point - h)) / (2.0 * h)
    half = h * 0.5
    fine = (evaluate(point + half) - evaluate(point - half)) / (2.0 * half)
    extrapolated = fine + (fine - coarse) / 3.0
    return DerivativeReport(
        derivative=finite_scalar("derivative", extrapolated),
        coarse_estimate=coarse,
        fine_estimate=fine,
        richardson_error_estimate=abs(extrapolated - fine),
        step=h,
        evaluations=4,
    )


@dataclass(frozen=True, slots=True)
class JacobianReport:
    jacobian: Matrix
    output: Vector
    steps: Vector
    evaluations: int


def finite_difference_jacobian(
    function: VectorFunction,
    point: Sequence[Real],
    *,
    relative_step: Real = 1e-6,
    minimum_step: Real = 1e-7,
) -> JacobianReport:
    center = finite_vector("point", point)
    rel = positive_scalar("relative_step", relative_step)
    floor = positive_scalar("minimum_step", minimum_step)
    output = finite_vector("output", function(center))
    rows = len(output)
    columns = len(center)
    steps = tuple(max(floor, rel * max(1.0, abs(value))) for value in center)
    jacobian = [[0.0] * columns for _ in range(rows)]
    evaluations = 1
    for column in range(columns):
        h = steps[column]
        plus = list(center)
        minus = list(center)
        plus[column] += h
        minus[column] -= h
        out_plus = finite_vector("output_plus", function(tuple(plus)))
        out_minus = finite_vector("output_minus", function(tuple(minus)))
        evaluations += 2
        if len(out_plus) != rows or len(out_minus) != rows:
            raise MathInvariantError(
                "function output dimension changed during Jacobian evaluation",
                reason="dimension_mismatch",
                field="function",
            )
        for row in range(rows):
            jacobian[row][column] = (out_plus[row] - out_minus[row]) / (2.0 * h)
    return JacobianReport(
        jacobian=tuple(tuple(finite_scalar("jacobian", value) for value in row) for row in jacobian),
        output=output,
        steps=steps,
        evaluations=evaluations,
    )


@dataclass(frozen=True, slots=True)
class GradientCheckReport:
    analytic: Vector
    numerical: Vector
    difference_l2: float
    maximum_absolute_error: float
    maximum_relative_error: float
    passed: bool


def check_gradient(
    function: ScalarVectorFunction,
    point: Sequence[Real],
    analytic_gradient: Sequence[Real],
    *,
    relative_step: Real = 1e-6,
    minimum_step: Real = 1e-7,
    absolute_tolerance: Real = 1e-6,
    relative_tolerance: Real = 1e-5,
) -> GradientCheckReport:
    center = finite_vector("point", point)
    analytic = finite_vector("analytic_gradient", analytic_gradient)
    if len(center) != len(analytic):
        raise MathInvariantError(
            "analytic gradient dimension mismatch",
            reason="dimension_mismatch",
            field="analytic_gradient",
        )
    rel_step = positive_scalar("relative_step", relative_step)
    floor = positive_scalar("minimum_step", minimum_step)
    abs_tol = positive_scalar("absolute_tolerance", absolute_tolerance)
    rel_tol = positive_scalar("relative_tolerance", relative_tolerance)
    numerical = []
    for index, value in enumerate(center):
        h = max(floor, rel_step * max(1.0, abs(value)))
        plus = list(center)
        minus = list(center)
        plus[index] += h
        minus[index] -= h
        fp = finite_scalar("function_value", function(tuple(plus)))
        fm = finite_scalar("function_value", function(tuple(minus)))
        numerical.append((fp - fm) / (2.0 * h))
    numerical_vector = finite_vector("numerical_gradient", numerical)
    differences = tuple(abs(a - b) for a, b in zip(analytic, numerical_vector))
    relative_errors = tuple(
        difference / max(abs_tol, abs(a), abs(b))
        for difference, a, b in zip(differences, analytic, numerical_vector)
    )
    passed = all(
        difference <= abs_tol + rel_tol * max(abs(a), abs(b))
        for difference, a, b in zip(differences, analytic, numerical_vector)
    )
    delta = tuple(a - b for a, b in zip(analytic, numerical_vector))
    return GradientCheckReport(
        analytic=analytic,
        numerical=numerical_vector,
        difference_l2=l2_norm(delta),
        maximum_absolute_error=max(differences, default=0.0),
        maximum_relative_error=max(relative_errors, default=0.0),
        passed=passed,
    )
