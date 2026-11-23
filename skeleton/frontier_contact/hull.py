"""Convex-hull membership for a handful of segment mass points.

The center of mass of positive masses is the convex combination with weights
``m_i / M``. ``point_in_convex_hull`` is the geometric test used to reject a
reported center that leaves that hull. No random sampling.
"""

from __future__ import annotations

import math

from skeleton.frontier_contact.errors import ContactRejected

_Point = tuple[float, float, float]


def _sub(a: _Point, b: _Point) -> _Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: _Point, b: _Point) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: _Point, b: _Point) -> _Point:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _length(a: _Point) -> float:
    return math.sqrt(_dot(a, a))


def _span(points: tuple[_Point, ...], tol: float) -> tuple[str, _Point | None]:
    origin = points[0]
    direction: _Point | None = None
    for point in points[1:]:
        delta = _sub(point, origin)
        if _length(delta) > tol:
            direction = delta
            break
    if direction is None:
        return "point", None
    normal: _Point | None = None
    for point in points[1:]:
        candidate = _cross(direction, _sub(point, origin))
        if _length(candidate) > tol:
            normal = candidate
            break
    if normal is None:
        return "line", direction
    scale = _length(normal)
    unit = (normal[0] / scale, normal[1] / scale, normal[2] / scale)
    for point in points:
        if abs(_dot(_sub(point, origin), unit)) > 1e-6:
            return "volume", unit
    return "plane", unit


def _on_segment(
    points: tuple[_Point, ...], query: _Point, direction: _Point, tol: float
) -> bool:
    origin = points[0]
    axis_length = _length(direction)
    axis = (
        direction[0] / axis_length,
        direction[1] / axis_length,
        direction[2] / axis_length,
    )
    coordinates = [_dot(_sub(point, origin), axis) for point in points]
    query_t = _dot(_sub(query, origin), axis)
    lateral = _sub(
        _sub(query, origin), (axis[0] * query_t, axis[1] * query_t, axis[2] * query_t)
    )
    if _length(lateral) > tol:
        return False
    return min(coordinates) - tol <= query_t <= max(coordinates) + tol


def _project_plane(
    points: tuple[_Point, ...], normal: _Point
) -> tuple[tuple[float, float], ...]:
    reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
    tangent = _cross(normal, reference)
    scale = _length(tangent)
    tangent = (tangent[0] / scale, tangent[1] / scale, tangent[2] / scale)
    bitangent = _cross(normal, tangent)
    origin = points[0]
    projected = []
    for point in points:
        delta = _sub(point, origin)
        projected.append((_dot(delta, tangent), _dot(delta, bitangent)))
    return tuple(projected)


def _query_plane(query: _Point, origin: _Point, normal: _Point) -> tuple[float, float]:
    reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
    tangent = _cross(normal, reference)
    scale = _length(tangent)
    tangent = (tangent[0] / scale, tangent[1] / scale, tangent[2] / scale)
    bitangent = _cross(normal, tangent)
    delta = _sub(query, origin)
    return _dot(delta, tangent), _dot(delta, bitangent)


def _monotone_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique = sorted(set(points))
    if len(unique) <= 2:
        return unique

    def chain(sequence: list[tuple[float, float]]) -> list[tuple[float, float]]:
        built: list[tuple[float, float]] = []
        for point in sequence:
            while len(built) >= 2:
                left = built[-2]
                mid = built[-1]
                cross = (mid[0] - left[0]) * (point[1] - left[1]) - (
                    mid[1] - left[1]
                ) * (point[0] - left[0])
                if cross >= 0.0:
                    break
                built.pop()
            built.append(point)
        return built

    lower = chain(unique)
    upper = chain(list(reversed(unique)))
    return lower[:-1] + upper[:-1]


def _in_polygon(
    point: tuple[float, float], polygon: list[tuple[float, float]], tol: float
) -> bool:
    if len(polygon) == 1:
        return math.hypot(point[0] - polygon[0][0], point[1] - polygon[0][1]) <= tol
    if len(polygon) == 2:
        return _on_segment_2d(polygon[0], polygon[1], point, tol)
    for index, start in enumerate(polygon):
        end = polygon[(index + 1) % len(polygon)]
        cross = (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (
            point[0] - start[0]
        )
        if cross < -tol:
            return False
    return True


def _on_segment_2d(
    start: tuple[float, float],
    end: tuple[float, float],
    point: tuple[float, float],
    tol: float,
) -> bool:
    edge = (end[0] - start[0], end[1] - start[1])
    length = math.hypot(edge[0], edge[1])
    if length <= tol:
        return math.hypot(point[0] - start[0], point[1] - start[1]) <= tol
    tangent = ((point[0] - start[0]) * edge[0] + (point[1] - start[1]) * edge[1]) / (
        length * length
    )
    if tangent < -tol or tangent > 1.0 + tol:
        return False
    closest = (start[0] + edge[0] * tangent, start[1] + edge[1] * tangent)
    return math.hypot(point[0] - closest[0], point[1] - closest[1]) <= tol


def _in_volume(points: tuple[_Point, ...], query: _Point, tol: float) -> bool:
    count = len(points)
    for i in range(count):
        for j in range(i + 1, count):
            for k in range(j + 1, count):
                edge_a = _sub(points[j], points[i])
                edge_b = _sub(points[k], points[i])
                normal = _cross(edge_a, edge_b)
                if _length(normal) <= 1e-12:
                    continue
                signs = []
                for index, point in enumerate(points):
                    if index in (i, j, k):
                        continue
                    signs.append(_dot(_sub(point, points[i]), normal))
                if not signs:
                    continue
                if max(signs) > tol and min(signs) < -tol:
                    continue
                query_side = _dot(_sub(query, points[i]), normal)
                if max(signs) <= tol and query_side > tol * max(1.0, _length(normal)):
                    return False
                if min(signs) >= -tol and query_side < -tol * max(1.0, _length(normal)):
                    return False
    return True


def point_in_convex_hull(
    points: tuple[_Point, ...] | list[_Point],
    query: _Point,
    *,
    tol: float = 1e-7,
) -> bool:
    """True when ``query`` lies in the convex hull of ``points``."""
    if (
        isinstance(tol, bool)
        or not isinstance(tol, (int, float))
        or not math.isfinite(float(tol))
        or tol < 0
    ):
        raise ContactRejected("hull tolerance out of range")
    if not points:
        return False
    cloud = tuple(points)
    for point in cloud:
        if len(point) != 3 or any(
            isinstance(axis, bool) or not isinstance(axis, (int, float))
            for axis in point
        ):
            raise ContactRejected("hull point must be a 3-vector")
        if any(isinstance(axis, float) and math.isnan(axis) for axis in point):
            raise ContactRejected("NaN")
    if len(query) != 3 or any(
        isinstance(axis, bool) or not isinstance(axis, (int, float)) for axis in query
    ):
        raise ContactRejected("hull point must be a 3-vector")
    if any(isinstance(axis, float) and math.isnan(axis) for axis in query):
        raise ContactRejected("NaN")
    kind, feature = _span(cloud, float(tol))
    if kind == "point":
        return _length(_sub(query, cloud[0])) <= tol
    if kind == "line":
        assert feature is not None
        return _on_segment(cloud, query, feature, float(tol))
    if kind == "plane":
        assert feature is not None
        height = _dot(_sub(query, cloud[0]), feature)
        if abs(height) > 1e-6:
            return False
        flat = list(_project_plane(cloud, feature))
        query_2d = _query_plane(query, cloud[0], feature)
        return _in_polygon(query_2d, _monotone_hull(flat), float(tol))
    return _in_volume(cloud, query, float(tol))
