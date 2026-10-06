"""Bezier curves via de Casteljau evaluation, derivatives, and subdivision."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector


@dataclass(frozen=True, slots=True)
class BezierCurve:
    control_points: tuple[Vector, ...]

    def __post_init__(self) -> None:
        if not self.control_points:
            raise MathInvariantError(
                "Bezier curve requires at least one control point",
                reason="empty_geometry",
                field="control_points",
            )
        points = tuple(
            finite_vector(f"control_points[{index}]", point)
            for index, point in enumerate(self.control_points)
        )
        dimension = len(points[0])
        if any(len(point) != dimension for point in points):
            raise MathInvariantError(
                "Bezier control points must have equal dimension",
                reason="dimension_mismatch",
                field="control_points",
            )
        object.__setattr__(self, "control_points", points)

    @property
    def degree(self) -> int:
        return len(self.control_points) - 1

    @property
    def dimension(self) -> int:
        return len(self.control_points[0])

    def evaluate(self, parameter: Real) -> Vector:
        t = finite_scalar("parameter", parameter)
        if not 0.0 <= t <= 1.0:
            raise MathInvariantError(
                "Bezier parameter must lie in [0, 1]",
                reason="extrapolation_forbidden",
                field="parameter",
            )
        level = [list(point) for point in self.control_points]
        while len(level) > 1:
            level = [
                [
                    (1.0 - t) * left[axis] + t * right[axis]
                    for axis in range(self.dimension)
                ]
                for left, right in zip(level, level[1:])
            ]
        return tuple(level[0])

    def derivative_curve(self, order: int = 1) -> "BezierCurve":
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            raise MathInvariantError(
                "Bezier derivative order must be a non-negative integer",
                reason="invalid_derivative_order",
                field="order",
            )
        if order == 0:
            return self
        if order > self.degree:
            return BezierCurve((tuple(0.0 for _ in range(self.dimension)),))
        points = self.control_points
        degree = self.degree
        for current_order in range(order):
            scale = degree - current_order
            points = tuple(
                tuple(scale * (right[axis] - left[axis]) for axis in range(self.dimension))
                for left, right in zip(points, points[1:])
            )
        return BezierCurve(points)

    def derivative(self, parameter: Real, order: int = 1) -> Vector:
        return self.derivative_curve(order).evaluate(parameter)

    def split(self, parameter: Real) -> tuple["BezierCurve", "BezierCurve"]:
        t = finite_scalar("parameter", parameter)
        if not 0.0 <= t <= 1.0:
            raise MathInvariantError(
                "Bezier split parameter must lie in [0, 1]",
                reason="extrapolation_forbidden",
                field="parameter",
            )
        levels = [[tuple(point) for point in self.control_points]]
        while len(levels[-1]) > 1:
            previous = levels[-1]
            next_level = [
                tuple(
                    (1.0 - t) * left[axis] + t * right[axis]
                    for axis in range(self.dimension)
                )
                for left, right in zip(previous, previous[1:])
            ]
            levels.append(next_level)
        left_points = tuple(level[0] for level in levels)
        right_points = tuple(level[-1] for level in reversed(levels))
        return BezierCurve(left_points), BezierCurve(right_points)

    def control_bounds(self) -> tuple[Vector, Vector]:
        lower = tuple(
            min(point[axis] for point in self.control_points)
            for axis in range(self.dimension)
        )
        upper = tuple(
            max(point[axis] for point in self.control_points)
            for axis in range(self.dimension)
        )
        return lower, upper
