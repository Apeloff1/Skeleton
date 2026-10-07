"""Tensor-product Bezier and B-spline surface reference geometry."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .bezier import BezierCurve
from .bsplines import bspline_basis
from .contracts import MathInvariantError, Vector, finite_vector


def _control_net(
    control_points: Sequence[Sequence[Sequence[Real]]],
) -> tuple[tuple[Vector, ...], ...]:
    if not control_points or not control_points[0]:
        raise MathInvariantError(
            "parametric surface requires a non-empty control net",
            reason="empty_geometry",
            field="control_points",
        )
    rows = tuple(
        tuple(
            finite_vector(f"control_points[{i}][{j}]", point)
            for j, point in enumerate(row)
        )
        for i, row in enumerate(control_points)
    )
    columns = len(rows[0])
    dimension = len(rows[0][0])
    if any(len(row) != columns for row in rows):
        raise MathInvariantError(
            "surface control net must be rectangular",
            reason="ragged_matrix",
            field="control_points",
        )
    if any(len(point) != dimension for row in rows for point in row):
        raise MathInvariantError(
            "surface control points must share dimension",
            reason="dimension_mismatch",
            field="control_points",
        )
    return rows


@dataclass(frozen=True, slots=True)
class BezierSurface:
    control_points: tuple[tuple[Vector, ...], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "control_points", _control_net(self.control_points))

    @property
    def degree_u(self) -> int:
        return len(self.control_points) - 1

    @property
    def degree_v(self) -> int:
        return len(self.control_points[0]) - 1

    def evaluate(self, u: Real, v: Real) -> Vector:
        along_v = tuple(BezierCurve(row).evaluate(v) for row in self.control_points)
        return BezierCurve(along_v).evaluate(u)

    def partial_u(self, u: Real, v: Real) -> Vector:
        if self.degree_u == 0:
            return tuple(0.0 for _ in self.control_points[0][0])
        derivative_net = tuple(
            tuple(
                tuple(
                    self.degree_u * (self.control_points[i + 1][j][axis] - self.control_points[i][j][axis])
                    for axis in range(len(self.control_points[0][0]))
                )
                for j in range(len(self.control_points[0]))
            )
            for i in range(self.degree_u)
        )
        return BezierSurface(derivative_net).evaluate(u, v)

    def partial_v(self, u: Real, v: Real) -> Vector:
        if self.degree_v == 0:
            return tuple(0.0 for _ in self.control_points[0][0])
        derivative_net = tuple(
            tuple(
                tuple(
                    self.degree_v * (row[j + 1][axis] - row[j][axis])
                    for axis in range(len(row[0]))
                )
                for j in range(self.degree_v)
            )
            for row in self.control_points
        )
        return BezierSurface(derivative_net).evaluate(u, v)


@dataclass(frozen=True, slots=True)
class BSplineSurface:
    control_points: tuple[tuple[Vector, ...], ...]
    knots_u: tuple[float, ...]
    knots_v: tuple[float, ...]
    degree_u: int
    degree_v: int

    def __post_init__(self) -> None:
        points = _control_net(self.control_points)
        for name, degree in (("degree_u", self.degree_u), ("degree_v", self.degree_v)):
            if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
                raise MathInvariantError(
                    "B-spline surface degrees must be non-negative integers",
                    reason="invalid_polynomial_degree",
                    field=name,
                )
        knots_u = finite_vector("knots_u", self.knots_u)
        knots_v = finite_vector("knots_v", self.knots_v)
        for name, knots in (("knots_u", knots_u), ("knots_v", knots_v)):
            if any(knots[index] < knots[index - 1] for index in range(1, len(knots))):
                raise MathInvariantError(
                    "B-spline surface knots must be non-decreasing",
                    reason="non_monotonic_nodes",
                    field=name,
                )
        expected_u = len(knots_u) - self.degree_u - 1
        expected_v = len(knots_v) - self.degree_v - 1
        if expected_u != len(points) or expected_v != len(points[0]):
            raise MathInvariantError(
                "B-spline surface knot vectors must match control-net dimensions",
                reason="dimension_mismatch",
                field="knots",
            )
        object.__setattr__(self, "control_points", points)
        object.__setattr__(self, "knots_u", knots_u)
        object.__setattr__(self, "knots_v", knots_v)

    def evaluate(self, u: Real, v: Real) -> Vector:
        basis_u = bspline_basis(self.knots_u, self.degree_u, u)
        basis_v = bspline_basis(self.knots_v, self.degree_v, v)
        dimension = len(self.control_points[0][0])
        return tuple(
            sum(
                basis_u.values[i] * basis_v.values[j] * self.control_points[i][j][axis]
                for i in range(len(self.control_points))
                for j in range(len(self.control_points[0]))
            )
            for axis in range(dimension)
        )
