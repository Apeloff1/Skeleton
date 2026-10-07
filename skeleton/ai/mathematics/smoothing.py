"""Local polynomial smoothing and derivative estimation references."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector, positive_scalar
from .decompositions import least_squares


@dataclass(frozen=True, slots=True)
class LocalPolynomialReport:
    values: Vector
    window: int
    degree: int
    derivative_order: int
    spacing: float


def _factorial_ratio(power: int, derivative: int) -> float:
    value = 1.0
    for item in range(power - derivative + 1, power + 1):
        value *= item
    return value


def local_polynomial_smooth(
    values: Sequence[Real],
    *,
    window: int = 5,
    degree: int = 2,
    derivative_order: int = 0,
    spacing: Real = 1.0,
) -> LocalPolynomialReport:
    observations = finite_vector("values", values)
    if isinstance(window, bool) or not isinstance(window, int) or window < 3 or window % 2 == 0:
        raise MathInvariantError(
            "local-polynomial window must be an odd integer >= 3",
            reason="invalid_window_length",
            field="window",
        )
    if window > len(observations):
        raise MathInvariantError(
            "local-polynomial window exceeds observation count",
            reason="invalid_window_length",
            field="window",
        )
    if isinstance(degree, bool) or not isinstance(degree, int) or not 0 <= degree < window:
        raise MathInvariantError(
            "polynomial degree must lie in [0, window)",
            reason="invalid_polynomial_degree",
            field="degree",
        )
    if (
        isinstance(derivative_order, bool)
        or not isinstance(derivative_order, int)
        or not 0 <= derivative_order <= degree
    ):
        raise MathInvariantError(
            "derivative_order must lie in [0, degree]",
            reason="invalid_derivative_order",
            field="derivative_order",
        )
    h = positive_scalar("spacing", spacing)
    half = window // 2
    output = []

    for center in range(len(observations)):
        start = min(max(0, center - half), len(observations) - window)
        end = start + window
        offsets = tuple((index - center) * h for index in range(start, end))
        design = tuple(
            tuple(offset**power for power in range(degree + 1))
            for offset in offsets
        )
        target = observations[start:end]
        fit = least_squares(design, target, rank_tolerance=1e-14)
        coefficient = fit.solution[derivative_order]
        derivative = coefficient * math.factorial(derivative_order)
        output.append(derivative)

    return LocalPolynomialReport(
        values=tuple(output),
        window=window,
        degree=degree,
        derivative_order=derivative_order,
        spacing=h,
    )


def savitzky_golay_smooth(
    values: Sequence[Real],
    *,
    window: int = 5,
    degree: int = 2,
) -> Vector:
    return local_polynomial_smooth(
        values,
        window=window,
        degree=degree,
        derivative_order=0,
    ).values


def savitzky_golay_derivative(
    values: Sequence[Real],
    *,
    window: int = 5,
    degree: int = 2,
    derivative_order: int = 1,
    spacing: Real = 1.0,
) -> Vector:
    return local_polynomial_smooth(
        values,
        window=window,
        degree=degree,
        derivative_order=derivative_order,
        spacing=spacing,
    ).values
