"""Polynomial algebra and deterministic complex-root reference solving."""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector


def _trim(coefficients: Sequence[Real]) -> Vector:
    values = list(finite_vector("coefficients", coefficients))
    while len(values) > 1 and values[-1] == 0.0:
        values.pop()
    return tuple(values)


def polynomial_evaluate(coefficients: Sequence[Real], x: Real | complex) -> complex:
    coeffs = _trim(coefficients)
    if isinstance(x, bool) or not isinstance(x, (int, float, complex)):
        raise MathInvariantError(
            "polynomial evaluation point must be numeric",
            reason="invalid_numeric_type",
            field="x",
        )
    point = complex(x)
    if not math.isfinite(point.real) or not math.isfinite(point.imag):
        raise MathInvariantError(
            "polynomial evaluation point must be finite",
            reason="non_finite_value",
            field="x",
        )
    result = 0j
    for coefficient in reversed(coeffs):
        result = result * point + coefficient
    if not math.isfinite(result.real) or not math.isfinite(result.imag):
        raise MathInvariantError(
            "polynomial evaluation became non-finite",
            reason="non_finite_result",
            field="polynomial",
        )
    return result


def polynomial_add(left: Sequence[Real], right: Sequence[Real]) -> Vector:
    a = _trim(left)
    b = _trim(right)
    size = max(len(a), len(b))
    return _trim(tuple(
        (a[index] if index < len(a) else 0.0)
        + (b[index] if index < len(b) else 0.0)
        for index in range(size)
    ))


def polynomial_multiply(left: Sequence[Real], right: Sequence[Real]) -> Vector:
    a = _trim(left)
    b = _trim(right)
    output = [0.0] * (len(a) + len(b) - 1)
    for i, left_value in enumerate(a):
        for j, right_value in enumerate(b):
            output[i + j] += left_value * right_value
    return _trim(tuple(output))


def polynomial_derivative(coefficients: Sequence[Real], order: int = 1) -> Vector:
    coeffs = _trim(coefficients)
    if isinstance(order, bool) or not isinstance(order, int) or order < 0:
        raise MathInvariantError(
            "polynomial derivative order must be a non-negative integer",
            reason="invalid_derivative_order",
            field="order",
        )
    result = coeffs
    for _ in range(order):
        if len(result) == 1:
            return (0.0,)
        result = tuple(index * result[index] for index in range(1, len(result)))
    return _trim(result)


def polynomial_integral(
    coefficients: Sequence[Real],
    *,
    constant: Real = 0.0,
) -> Vector:
    coeffs = _trim(coefficients)
    integration_constant = finite_scalar("constant", constant)
    return (integration_constant,) + tuple(
        coefficient / (index + 1)
        for index, coefficient in enumerate(coeffs)
    )


def polynomial_divmod(
    numerator: Sequence[Real],
    denominator: Sequence[Real],
    *,
    tolerance: Real = 1e-14,
) -> tuple[Vector, Vector]:
    num = list(_trim(numerator))
    den = _trim(denominator)
    tol = finite_scalar("tolerance", tolerance)
    if tol < 0.0:
        raise MathInvariantError(
            "polynomial division tolerance must be non-negative",
            reason="negative_tolerance",
            field="tolerance",
        )
    if len(den) == 1 and den[0] == 0.0:
        raise MathInvariantError(
            "polynomial denominator must be non-zero",
            reason="division_by_zero",
            field="denominator",
        )
    if len(num) < len(den):
        return (0.0,), tuple(num)
    quotient = [0.0] * (len(num) - len(den) + 1)
    lead = den[-1]
    while len(num) >= len(den):
        degree = len(num) - len(den)
        factor = num[-1] / lead
        quotient[degree] = factor
        for index in range(len(den)):
            num[degree + index] -= factor * den[index]
        while num and abs(num[-1]) <= tol:
            num.pop()
        if not num:
            break
    remainder = (0.0,) if not num else tuple(num)
    return _trim(tuple(quotient)), _trim(remainder)


@dataclass(frozen=True, slots=True)
class PolynomialRootsReport:
    roots: tuple[complex, ...]
    iterations: int
    converged: bool
    maximum_update: float
    maximum_residual: float


def polynomial_roots(
    coefficients: Sequence[Real],
    *,
    tolerance: Real = 1e-12,
    max_iterations: int = 500,
) -> PolynomialRootsReport:
    coeffs = _trim(coefficients)
    degree = len(coeffs) - 1
    tol = finite_scalar("tolerance", tolerance)
    if tol <= 0.0:
        raise MathInvariantError(
            "root tolerance must be positive",
            reason="invalid_tolerance",
            field="tolerance",
        )
    if isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise MathInvariantError(
            "max_iterations must be a positive integer",
            reason="invalid_iteration_limit",
            field="max_iterations",
        )
    if degree < 1:
        raise MathInvariantError(
            "constant polynomial has no finite root set",
            reason="constant_polynomial",
            field="coefficients",
        )
    if degree == 1:
        root = complex(-coeffs[0] / coeffs[1], 0.0)
        return PolynomialRootsReport((root,), 0, True, 0.0, 0.0)

    leading = coeffs[-1]
    monic = tuple(value / leading for value in coeffs)
    radius = 1.0 + max(abs(value) for value in monic[:-1])
    roots = [
        radius * cmath.exp(2j * math.pi * (index + 0.5) / degree)
        for index in range(degree)
    ]
    maximum_update = math.inf
    converged = False
    iterations = 0

    for iterations in range(1, max_iterations + 1):
        next_roots = roots.copy()
        maximum_update = 0.0
        for i, root in enumerate(roots):
            denominator = 1 + 0j
            for j, other in enumerate(roots):
                if i != j:
                    denominator *= root - other
            if abs(denominator) <= 1e-30:
                raise MathInvariantError(
                    "Durand-Kerner denominator collapsed; repeated or unresolved roots suspected",
                    reason="root_iteration_breakdown",
                    field="roots",
                )
            correction = polynomial_evaluate(monic, root) / denominator
            next_roots[i] = root - correction
            maximum_update = max(maximum_update, abs(correction))
        roots = next_roots
        if maximum_update <= tol:
            converged = True
            break

    roots_tuple = tuple(sorted(roots, key=lambda value: (round(value.real, 14), round(value.imag, 14))))
    maximum_residual = max(abs(polynomial_evaluate(coeffs, root)) for root in roots_tuple)
    return PolynomialRootsReport(
        roots=roots_tuple,
        iterations=iterations,
        converged=converged,
        maximum_update=maximum_update,
        maximum_residual=maximum_residual,
    )
