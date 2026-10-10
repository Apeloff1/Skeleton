"""Shape-preserving monotone cubic Hermite interpolation."""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector


@dataclass(frozen=True, slots=True)
class MonotoneCubicInterpolator:
    knots: Vector
    values: Vector
    slopes: Vector

    def _interval(self, x: float) -> tuple[int, float, float]:
        if x < self.knots[0] or x > self.knots[-1]:
            raise MathInvariantError(
                "point lies outside monotone interpolation domain",
                reason="extrapolation_forbidden",
                field="x",
            )
        if x == self.knots[-1]:
            index = len(self.knots) - 2
        else:
            index = max(0, bisect.bisect_right(self.knots, x) - 1)
        width = self.knots[index + 1] - self.knots[index]
        t = (x - self.knots[index]) / width
        return index, width, t

    def evaluate(self, x: Real) -> float:
        point = finite_scalar("x", x)
        index, width, t = self._interval(point)
        y0 = self.values[index]
        y1 = self.values[index + 1]
        m0 = self.slopes[index]
        m1 = self.slopes[index + 1]
        h00 = 2.0 * t**3 - 3.0 * t**2 + 1.0
        h10 = t**3 - 2.0 * t**2 + t
        h01 = -2.0 * t**3 + 3.0 * t**2
        h11 = t**3 - t**2
        return finite_scalar(
            "interpolated_value",
            h00 * y0 + h10 * width * m0 + h01 * y1 + h11 * width * m1,
        )

    def derivative(self, x: Real) -> float:
        point = finite_scalar("x", x)
        index, width, t = self._interval(point)
        y0 = self.values[index]
        y1 = self.values[index + 1]
        m0 = self.slopes[index]
        m1 = self.slopes[index + 1]
        derivative_t = (
            (6.0 * t**2 - 6.0 * t) * y0
            + (3.0 * t**2 - 4.0 * t + 1.0) * width * m0
            + (-6.0 * t**2 + 6.0 * t) * y1
            + (3.0 * t**2 - 2.0 * t) * width * m1
        )
        return finite_scalar("interpolated_derivative", derivative_t / width)


def monotone_cubic_interpolator(
    knots: Sequence[Real],
    values: Sequence[Real],
) -> MonotoneCubicInterpolator:
    x = finite_vector("knots", knots)
    y = finite_vector("values", values)
    if len(x) != len(y):
        raise MathInvariantError(
            "monotone knots and values must have equal length",
            reason="dimension_mismatch",
            field="samples",
        )
    if len(x) < 2:
        raise MathInvariantError(
            "monotone cubic interpolation requires at least two knots",
            reason="insufficient_observations",
            field="knots",
        )
    widths = []
    deltas = []
    for index in range(len(x) - 1):
        width = x[index + 1] - x[index]
        if width <= 0.0:
            raise MathInvariantError(
                "monotone interpolation knots must be strictly increasing",
                reason="non_monotonic_nodes",
                field=f"knots[{index + 1}]",
            )
        widths.append(width)
        deltas.append((y[index + 1] - y[index]) / width)

    if len(x) == 2:
        slopes = (deltas[0], deltas[0])
        return MonotoneCubicInterpolator(x, y, slopes)

    slopes = [0.0] * len(x)
    slopes[0] = deltas[0]
    slopes[-1] = deltas[-1]
    for index in range(1, len(x) - 1):
        left = deltas[index - 1]
        right = deltas[index]
        slopes[index] = 0.0 if left * right <= 0.0 else 0.5 * (left + right)

    for index, delta in enumerate(deltas):
        if delta == 0.0:
            slopes[index] = 0.0
            slopes[index + 1] = 0.0
            continue
        alpha = slopes[index] / delta
        beta = slopes[index + 1] / delta
        magnitude = alpha * alpha + beta * beta
        if magnitude > 9.0:
            tau = 3.0 / math.sqrt(magnitude)
            slopes[index] = tau * alpha * delta
            slopes[index + 1] = tau * beta * delta

    return MonotoneCubicInterpolator(x, y, tuple(slopes))
