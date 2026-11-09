"""B-spline basis and curve evaluation reference primitives."""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_scalar, finite_vector


def _validated_knots(knots: Sequence[Real], degree: int) -> Vector:
    values = finite_vector("knots", knots)
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise MathInvariantError(
            "B-spline degree must be a non-negative integer",
            reason="invalid_polynomial_degree",
            field="degree",
        )
    if len(values) < degree + 2:
        raise MathInvariantError(
            "knot vector is too short for requested B-spline degree",
            reason="insufficient_knots",
            field="knots",
        )
    for index in range(1, len(values)):
        if values[index] < values[index - 1]:
            raise MathInvariantError(
                "B-spline knots must be non-decreasing",
                reason="non_monotonic_nodes",
                field=f"knots[{index}]",
            )
    if values[degree] >= values[-degree - 1]:
        raise MathInvariantError(
            "B-spline active parameter domain must have positive width",
            reason="degenerate_domain",
            field="knots",
        )
    return values


def clamped_uniform_knots(control_count: int, degree: int) -> Vector:
    if isinstance(control_count, bool) or not isinstance(control_count, int) or control_count < 1:
        raise MathInvariantError(
            "control_count must be a positive integer",
            reason="invalid_count",
            field="control_count",
        )
    if isinstance(degree, bool) or not isinstance(degree, int) or degree < 0:
        raise MathInvariantError(
            "degree must be a non-negative integer",
            reason="invalid_polynomial_degree",
            field="degree",
        )
    if control_count <= degree:
        raise MathInvariantError(
            "B-spline requires control_count > degree",
            reason="insufficient_control_points",
            field="control_count",
        )
    interior_count = control_count - degree - 1
    knots = [0.0] * (degree + 1)
    if interior_count > 0:
        denominator = interior_count + 1
        knots.extend(index / denominator for index in range(1, interior_count + 1))
    knots.extend([1.0] * (degree + 1))
    return tuple(knots)


@dataclass(frozen=True, slots=True)
class BSplineBasisReport:
    values: Vector
    parameter: float
    degree: int
    partition_sum: float
    active_indices: tuple[int, ...]


def bspline_basis(
    knots: Sequence[Real],
    degree: int,
    parameter: Real,
) -> BSplineBasisReport:
    knot_vector = _validated_knots(knots, degree)
    x = finite_scalar("parameter", parameter)
    basis_count = len(knot_vector) - degree - 1
    domain_start = knot_vector[degree]
    domain_end = knot_vector[-degree - 1]
    if x < domain_start or x > domain_end:
        raise MathInvariantError(
            "B-spline parameter lies outside the active knot domain",
            reason="extrapolation_forbidden",
            field="parameter",
        )

    level = [0.0] * (len(knot_vector) - 1)
    if x == domain_end:
        level[basis_count - 1] = 1.0
    else:
        for index in range(len(level)):
            if knot_vector[index] <= x < knot_vector[index + 1]:
                level[index] = 1.0

    for order in range(1, degree + 1):
        next_level = [0.0] * (len(knot_vector) - order - 1)
        for index in range(len(next_level)):
            left = 0.0
            left_denominator = knot_vector[index + order] - knot_vector[index]
            if left_denominator > 0.0:
                left = (x - knot_vector[index]) / left_denominator * level[index]

            right = 0.0
            right_denominator = knot_vector[index + order + 1] - knot_vector[index + 1]
            if right_denominator > 0.0:
                right = (
                    (knot_vector[index + order + 1] - x)
                    / right_denominator
                    * level[index + 1]
                )
            next_level[index] = left + right
        level = next_level

    values = tuple(level[:basis_count])
    partition = sum(values)
    active = tuple(index for index, value in enumerate(values) if value != 0.0)
    return BSplineBasisReport(
        values=values,
        parameter=x,
        degree=degree,
        partition_sum=partition,
        active_indices=active,
    )


def bspline_curve(
    control_points: Sequence[Sequence[Real]],
    knots: Sequence[Real],
    degree: int,
    parameter: Real,
) -> Vector:
    if not control_points:
        raise MathInvariantError(
            "B-spline curve requires control points",
            reason="empty_geometry",
            field="control_points",
        )
    points = tuple(
        finite_vector(f"control_points[{index}]", point)
        for index, point in enumerate(control_points)
    )
    dimension = len(points[0])
    if any(len(point) != dimension for point in points):
        raise MathInvariantError(
            "B-spline control points must have consistent dimension",
            reason="dimension_mismatch",
            field="control_points",
        )
    report = bspline_basis(knots, degree, parameter)
    if len(report.values) != len(points):
        raise MathInvariantError(
            "B-spline knot vector does not match control-point count",
            reason="dimension_mismatch",
            field="knots",
        )
    return tuple(
        sum(weight * point[axis] for weight, point in zip(report.values, points))
        for axis in range(dimension)
    )
