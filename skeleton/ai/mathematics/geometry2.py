"""Deterministic planar computational-geometry reference primitives."""
from __future__ import annotations

from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, finite_vector


Point2D = tuple[float, float]


def _point(name: str, value: Sequence[Real]) -> Point2D:
    point = finite_vector(name, value)
    if len(point) != 2:
        raise MathInvariantError(
            "planar geometry points must be two-dimensional",
            reason="dimension_mismatch",
            field=name,
        )
    return point[0], point[1]


def orientation(a: Sequence[Real], b: Sequence[Real], c: Sequence[Real]) -> float:
    p = _point("a", a)
    q = _point("b", b)
    r = _point("c", c)
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])


def convex_hull(points: Sequence[Sequence[Real]]) -> tuple[Point2D, ...]:
    if not points:
        raise MathInvariantError(
            "convex hull requires at least one point",
            reason="empty_geometry",
            field="points",
        )
    unique = sorted({_point(f"points[{index}]", point) for index, point in enumerate(points)})
    if len(unique) <= 2:
        return tuple(unique)

    def cross(o: Point2D, a: Point2D, b: Point2D) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point2D] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)
    upper: list[Point2D] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)
    return tuple(lower[:-1] + upper[:-1])


def signed_polygon_area(points: Sequence[Sequence[Real]]) -> float:
    polygon = tuple(_point(f"points[{index}]", point) for index, point in enumerate(points))
    if len(polygon) < 3:
        raise MathInvariantError(
            "polygon area requires at least three points",
            reason="insufficient_geometry",
            field="points",
        )
    twice = sum(
        polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
        - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
        for index in range(len(polygon))
    )
    return 0.5 * twice


def polygon_area(points: Sequence[Sequence[Real]]) -> float:
    return abs(signed_polygon_area(points))


def polygon_centroid(points: Sequence[Sequence[Real]]) -> Point2D:
    polygon = tuple(_point(f"points[{index}]", point) for index, point in enumerate(points))
    area = signed_polygon_area(polygon)
    if area == 0.0:
        raise MathInvariantError(
            "polygon centroid is undefined for zero-area polygon",
            reason="degenerate_geometry",
            field="points",
        )
    cx = 0.0
    cy = 0.0
    for index in range(len(polygon)):
        current = polygon[index]
        following = polygon[(index + 1) % len(polygon)]
        cross = current[0] * following[1] - following[0] * current[1]
        cx += (current[0] + following[0]) * cross
        cy += (current[1] + following[1]) * cross
    factor = 1.0 / (6.0 * area)
    return cx * factor, cy * factor


def point_in_polygon(
    point: Sequence[Real],
    polygon: Sequence[Sequence[Real]],
    *,
    include_boundary: bool = True,
) -> bool:
    p = _point("point", point)
    vertices = tuple(_point(f"polygon[{index}]", item) for index, item in enumerate(polygon))
    if len(vertices) < 3:
        raise MathInvariantError(
            "point-in-polygon requires at least three vertices",
            reason="insufficient_geometry",
            field="polygon",
        )

    inside = False
    for index in range(len(vertices)):
        a = vertices[index]
        b = vertices[(index + 1) % len(vertices)]
        cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(cross) <= 1e-14:
            if (
                min(a[0], b[0]) - 1e-14 <= p[0] <= max(a[0], b[0]) + 1e-14
                and min(a[1], b[1]) - 1e-14 <= p[1] <= max(a[1], b[1]) + 1e-14
            ):
                return include_boundary
        intersects = ((a[1] > p[1]) != (b[1] > p[1]))
        if intersects:
            x_cross = (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
            if p[0] < x_cross:
                inside = not inside
    return inside
