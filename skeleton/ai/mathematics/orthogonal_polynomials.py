"""Orthogonal-polynomial and Chebyshev-series reference evaluation."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Callable

from .contracts import MathInvariantError, Vector, finite_scalar


def _degree(name: str, degree: int) -> int:
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise MathInvariantError(
            f"{name} degree must be a non-negative integer",
            reason="invalid_polynomial_degree",
            field="degree",
        )
    return degree


def chebyshev_t(degree: int, x: Real) -> float:
    n = _degree("Chebyshev", degree)
    point = finite_scalar("x", x)
    if n == 0:
        return 1.0
    if n == 1:
        return point
    previous = 1.0
    current = point
    for _ in range(2, n + 1):
        previous, current = current, 2.0 * point * current - previous
    return current


def legendre_p(degree: int, x: Real) -> float:
    n = _degree("Legendre", degree)
    point = finite_scalar("x", x)
    if n == 0:
        return 1.0
    if n == 1:
        return point
    previous = 1.0
    current = point
    for k in range(2, n + 1):
        previous, current = (
            current,
            ((2 * k - 1) * point * current - (k - 1) * previous) / k,
        )
    return current


def probabilists_hermite(degree: int, x: Real) -> float:
    n = _degree("Hermite", degree)
    point = finite_scalar("x", x)
    if n == 0:
        return 1.0
    if n == 1:
        return point
    previous = 1.0
    current = point
    for k in range(1, n):
        previous, current = current, point * current - k * previous
    return current


def clenshaw_chebyshev(coefficients: Vector, x: Real) -> float:
    if not coefficients:
        raise MathInvariantError(
            "Chebyshev coefficient vector must not be empty",
            reason="empty_vector",
            field="coefficients",
        )
    point = finite_scalar("x", x)
    b1 = 0.0
    b2 = 0.0
    for coefficient in reversed(coefficients[1:]):
        b0 = 2.0 * point * b1 - b2 + coefficient
        b2, b1 = b1, b0
    return coefficients[0] + point * b1 - b2


@dataclass(frozen=True, slots=True)
class ChebyshevSeries:
    coefficients: Vector
    lower: float
    upper: float
    sample_count: int

    def evaluate(self, x: Real) -> float:
        point = finite_scalar("x", x)
        if not self.lower <= point <= self.upper:
            raise MathInvariantError(
                "Chebyshev series evaluation lies outside fit interval",
                reason="extrapolation_forbidden",
                field="x",
            )
        scaled = (2.0 * point - (self.upper + self.lower)) / (self.upper - self.lower)
        return clenshaw_chebyshev(self.coefficients, scaled)


def fit_chebyshev_series(
    function: Callable[[float], Real],
    degree: int,
    *,
    lower: Real = -1.0,
    upper: Real = 1.0,
) -> ChebyshevSeries:
    n = _degree("Chebyshev series", degree)
    lo = finite_scalar("lower", lower)
    hi = finite_scalar("upper", upper)
    if hi <= lo:
        raise MathInvariantError(
            "Chebyshev fit interval must satisfy lower < upper",
            reason="invalid_interval",
            field="bounds",
        )
    count = n + 1
    samples: list[tuple[float, float]] = []
    for j in range(count):
        theta = math.pi * (j + 0.5) / count
        scaled = math.cos(theta)
        x = 0.5 * (lo + hi) + 0.5 * (hi - lo) * scaled
        value = finite_scalar("function_value", function(x))
        samples.append((theta, value))

    coefficients = []
    for k in range(count):
        total = sum(value * math.cos(k * theta) for theta, value in samples)
        coefficient = (1.0 / count if k == 0 else 2.0 / count) * total
        coefficients.append(coefficient)
    return ChebyshevSeries(tuple(coefficients), lo, hi, count)
