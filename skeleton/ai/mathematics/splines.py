"""Natural cubic spline interpolation with exact interval integrals."""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector


@dataclass(frozen=True, slots=True)
class NaturalCubicSpline:
    knots: Vector
    a: Vector
    b: Vector
    c: Vector
    d: Vector

    def _interval(self, x: float, extrapolation: str) -> tuple[int, float]:
        if extrapolation not in {"error", "clamp"}:
            raise MathInvariantError(
                "spline extrapolation must be error or clamp",
                reason="invalid_extrapolation_policy",
                field="extrapolation",
            )
        point = x
        if point < self.knots[0]:
            if extrapolation == "error":
                raise MathInvariantError(
                    "point lies below spline domain",
                    reason="extrapolation_forbidden",
                    field="x",
                )
            point = self.knots[0]
        elif point > self.knots[-1]:
            if extrapolation == "error":
                raise MathInvariantError(
                    "point lies above spline domain",
                    reason="extrapolation_forbidden",
                    field="x",
                )
            point = self.knots[-1]
        if point == self.knots[-1]:
            index = len(self.knots) - 2
        else:
            index = bisect.bisect_right(self.knots, point) - 1
            index = max(0, min(len(self.a) - 1, index))
        return index, point - self.knots[index]

    def evaluate(self, x: Real, *, extrapolation: str = "error") -> float:
        point = finite_scalar("x", x)
        index, dx = self._interval(point, extrapolation)
        return finite_scalar(
            "spline_value",
            self.a[index]
            + self.b[index] * dx
            + self.c[index] * dx * dx
            + self.d[index] * dx * dx * dx,
        )

    def derivative(self, x: Real, *, extrapolation: str = "error") -> float:
        point = finite_scalar("x", x)
        index, dx = self._interval(point, extrapolation)
        return finite_scalar(
            "spline_derivative",
            self.b[index] + 2.0 * self.c[index] * dx + 3.0 * self.d[index] * dx * dx,
        )

    def second_derivative(self, x: Real, *, extrapolation: str = "error") -> float:
        point = finite_scalar("x", x)
        index, dx = self._interval(point, extrapolation)
        return finite_scalar(
            "spline_second_derivative",
            2.0 * self.c[index] + 6.0 * self.d[index] * dx,
        )

    def integral(self, lower: Real, upper: Real) -> float:
        start = finite_scalar("lower", lower)
        end = finite_scalar("upper", upper)
        if start == end:
            return 0.0
        sign = 1.0
        if end < start:
            start, end = end, start
            sign = -1.0
        if start < self.knots[0] or end > self.knots[-1]:
            raise MathInvariantError(
                "spline integral bounds must lie inside the knot domain",
                reason="extrapolation_forbidden",
                field="bounds",
            )

        def primitive(index: int, dx: float) -> float:
            return (
                self.a[index] * dx
                + 0.5 * self.b[index] * dx * dx
                + (self.c[index] / 3.0) * dx**3
                + 0.25 * self.d[index] * dx**4
            )

        total = 0.0
        cursor = start
        while cursor < end:
            if cursor == self.knots[-1]:
                break
            index = bisect.bisect_right(self.knots, cursor) - 1
            index = max(0, min(len(self.a) - 1, index))
            interval_end = min(end, self.knots[index + 1])
            left_dx = cursor - self.knots[index]
            right_dx = interval_end - self.knots[index]
            total += primitive(index, right_dx) - primitive(index, left_dx)
            cursor = interval_end
        return sign * finite_scalar("spline_integral", total)


def natural_cubic_spline(
    knots: Sequence[Real],
    values: Sequence[Real],
) -> NaturalCubicSpline:
    x = finite_vector("knots", knots)
    y = finite_vector("values", values)
    if len(x) != len(y):
        raise MathInvariantError(
            "spline knots and values must have equal length",
            reason="dimension_mismatch",
            field="samples",
        )
    if len(x) < 2:
        raise MathInvariantError(
            "natural cubic spline requires at least two knots",
            reason="insufficient_observations",
            field="knots",
        )
    for index in range(1, len(x)):
        if x[index] <= x[index - 1]:
            raise MathInvariantError(
                "spline knots must be strictly increasing",
                reason="non_monotonic_nodes",
                field=f"knots[{index}]",
            )
    n = len(x)
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    alpha = [0.0] * n
    for i in range(1, n - 1):
        alpha[i] = (
            3.0 / h[i] * (y[i + 1] - y[i])
            - 3.0 / h[i - 1] * (y[i] - y[i - 1])
        )

    l = [1.0] * n
    mu = [0.0] * n
    z = [0.0] * n
    for i in range(1, n - 1):
        l[i] = 2.0 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1]
        if l[i] == 0.0:
            raise MathInvariantError(
                "spline tridiagonal system became singular",
                reason="singular_matrix",
                field="knots",
            )
        mu[i] = h[i] / l[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]

    c = [0.0] * n
    b = [0.0] * (n - 1)
    d = [0.0] * (n - 1)
    a = list(y[:-1])
    for j in range(n - 2, -1, -1):
        c[j] = z[j] - mu[j] * c[j + 1]
        b[j] = (
            (y[j + 1] - y[j]) / h[j]
            - h[j] * (c[j + 1] + 2.0 * c[j]) / 3.0
        )
        d[j] = (c[j + 1] - c[j]) / (3.0 * h[j])

    return NaturalCubicSpline(
        knots=x,
        a=tuple(a),
        b=tuple(b),
        c=tuple(c[:-1]),
        d=tuple(d),
    )
