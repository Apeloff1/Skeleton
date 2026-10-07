"""Finite conservative interval arithmetic reference primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

from .contracts import MathInvariantError, finite_scalar


def _down(value: float) -> float:
    candidate = math.nextafter(value, -math.inf)
    if not math.isfinite(candidate):
        raise MathInvariantError(
            "interval lower rounding overflowed",
            reason="non_finite_result",
            field="interval",
        )
    return candidate


def _up(value: float) -> float:
    candidate = math.nextafter(value, math.inf)
    if not math.isfinite(candidate):
        raise MathInvariantError(
            "interval upper rounding overflowed",
            reason="non_finite_result",
            field="interval",
        )
    return candidate


@dataclass(frozen=True, slots=True)
class Interval:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        lower = finite_scalar("lower", self.lower)
        upper = finite_scalar("upper", self.upper)
        if lower > upper:
            raise MathInvariantError(
                "interval lower bound must not exceed upper bound",
                reason="invalid_interval",
                field="interval",
            )
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)

    @classmethod
    def point(cls, value: Real) -> "Interval":
        x = finite_scalar("value", value)
        return cls(x, x)

    @property
    def width(self) -> float:
        return self.upper - self.lower

    @property
    def midpoint(self) -> float:
        return self.lower + 0.5 * (self.upper - self.lower)

    def contains(self, value: Real) -> bool:
        x = finite_scalar("value", value)
        return self.lower <= x <= self.upper

    def __add__(self, other: "Interval | Real") -> "Interval":
        right = other if isinstance(other, Interval) else Interval.point(other)
        return Interval(_down(self.lower + right.lower), _up(self.upper + right.upper))

    __radd__ = __add__

    def __sub__(self, other: "Interval | Real") -> "Interval":
        right = other if isinstance(other, Interval) else Interval.point(other)
        return Interval(_down(self.lower - right.upper), _up(self.upper - right.lower))

    def __rsub__(self, other: Real) -> "Interval":
        return Interval.point(other) - self

    def __mul__(self, other: "Interval | Real") -> "Interval":
        right = other if isinstance(other, Interval) else Interval.point(other)
        products = (
            self.lower * right.lower,
            self.lower * right.upper,
            self.upper * right.lower,
            self.upper * right.upper,
        )
        return Interval(_down(min(products)), _up(max(products)))

    __rmul__ = __mul__

    def reciprocal(self) -> "Interval":
        if self.lower <= 0.0 <= self.upper:
            raise MathInvariantError(
                "interval reciprocal is undefined when interval contains zero",
                reason="division_by_zero_interval",
                field="interval",
            )
        values = (1.0 / self.lower, 1.0 / self.upper)
        return Interval(_down(min(values)), _up(max(values)))

    def __truediv__(self, other: "Interval | Real") -> "Interval":
        right = other if isinstance(other, Interval) else Interval.point(other)
        return self * right.reciprocal()

    def __rtruediv__(self, other: Real) -> "Interval":
        return Interval.point(other) / self

    def square(self) -> "Interval":
        if self.lower <= 0.0 <= self.upper:
            return Interval(0.0, _up(max(self.lower * self.lower, self.upper * self.upper)))
        values = (self.lower * self.lower, self.upper * self.upper)
        return Interval(_down(min(values)), _up(max(values)))

    def sqrt(self) -> "Interval":
        if self.lower < 0.0:
            raise MathInvariantError(
                "interval square root requires non-negative support",
                reason="domain_error",
                field="interval",
            )
        return Interval(_down(math.sqrt(self.lower)) if self.lower else 0.0, _up(math.sqrt(self.upper)))

    def exp(self) -> "Interval":
        return Interval(_down(math.exp(self.lower)), _up(math.exp(self.upper)))

    def log(self) -> "Interval":
        if self.lower <= 0.0:
            raise MathInvariantError(
                "interval logarithm requires strictly positive support",
                reason="domain_error",
                field="interval",
            )
        return Interval(_down(math.log(self.lower)), _up(math.log(self.upper)))


def interval_hull(left: Interval, right: Interval) -> Interval:
    return Interval(min(left.lower, right.lower), max(left.upper, right.upper))


def interval_intersection(left: Interval, right: Interval) -> Interval | None:
    lower = max(left.lower, right.lower)
    upper = min(left.upper, right.upper)
    return None if lower > upper else Interval(lower, upper)
