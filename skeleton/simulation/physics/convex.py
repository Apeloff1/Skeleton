"""Bounded deterministic convex support-map queries using GJK and EPA.

GJK establishes whether the Minkowski difference contains the origin. EPA expands
an intersecting tetrahedral simplex to recover a penetration normal, depth, and
witness points on both original shapes.

The implementation is deliberately a query kernel first. Analytic narrow-phase
paths remain authoritative until each convex pairing has dedicated regression
coverage.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import RigidBody
from .errors import ConvexQueryError, PhysicsValidationError
from .math3d import EPSILON, Vec3
from .shapes import PlaneShape

MAX_GJK_ITERATIONS = 128
MAX_EPA_ITERATIONS = 128
MAX_EPA_VERTICES = 256
MAX_EPA_FACES = 512
_GJK_DIRECTION_EPSILON_SQ = 1.0e-24
_DUPLICATE_SUPPORT_EPSILON_SQ = 1.0e-20


@dataclass(frozen=True, slots=True)
class SupportVertex:
    point: Vec3
    point_a: Vec3
    point_b: Vec3

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, Vec3)
            for value in (self.point, self.point_a, self.point_b)
        ):
            raise PhysicsValidationError("support vertex values must be Vec3")
        if not self.point.almost_equal(
            self.point_a - self.point_b,
            tolerance=1.0e-9,
        ):
            raise PhysicsValidationError(
                "support vertex Minkowski point mismatch"
            )


@dataclass(frozen=True, slots=True)
class GJKResult:
    intersects: bool
    iterations: int
    simplex: tuple[SupportVertex, ...]
    separating_direction: Vec3

    def __post_init__(self) -> None:
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 0
        ):
            raise PhysicsValidationError(
                "GJK iterations must be non-negative integer"
            )
        if not self.simplex:
            raise PhysicsValidationError("GJK result requires simplex")
        if not 1 <= len(self.simplex) <= 4:
            raise PhysicsValidationError("GJK simplex size outside [1, 4]")


@dataclass(frozen=True, slots=True)
class GJKDistanceResult:
    intersects: bool
    distance: float
    normal: Vec3
    point_a: Vec3
    point_b: Vec3
    iterations: int
    simplex: tuple[SupportVertex, ...]
    weights: tuple[float, ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.distance, bool)
            or not isinstance(self.distance, (int, float))
            or not math.isfinite(float(self.distance))
            or float(self.distance) < 0.0
        ):
            raise PhysicsValidationError(
                "GJK distance must be finite and non-negative"
            )
        object.__setattr__(self, "distance", float(self.distance))
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 0
        ):
            raise PhysicsValidationError(
                "GJK distance iterations must be non-negative integer"
            )
        if not self.simplex or not 1 <= len(self.simplex) <= 4:
            raise PhysicsValidationError(
                "GJK distance simplex size outside [1, 4]"
            )
        if len(self.weights) != len(self.simplex):
            raise PhysicsValidationError(
                "GJK distance weights must match simplex"
            )
        if any(
            not math.isfinite(weight) or weight < -1.0e-10
            for weight in self.weights
        ):
            raise PhysicsValidationError(
                "GJK distance weights must be finite and non-negative"
            )
        if abs(sum(self.weights) - 1.0) > 1.0e-8:
            raise PhysicsValidationError(
                "GJK distance weights must sum to one"
            )
        if self.intersects:
            if self.distance > 1.0e-8:
                raise PhysicsValidationError(
                    "intersecting GJK distance must be zero"
                )
        elif self.distance > 0.0:
            object.__setattr__(self, "normal", self.normal.normalized())


@dataclass(frozen=True, slots=True)
class EPAPenetration:
    normal: Vec3
    depth: float
    point_a: Vec3
    point_b: Vec3
    contact_point: Vec3
    iterations: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "normal", self.normal.normalized())
        if (
            isinstance(self.depth, bool)
            or not isinstance(self.depth, (int, float))
            or not math.isfinite(float(self.depth))
            or float(self.depth) < 0.0
        ):
            raise PhysicsValidationError(
                "EPA depth must be finite and non-negative"
            )
        object.__setattr__(self, "depth", float(self.depth))
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 0
        ):
            raise PhysicsValidationError(
                "EPA iterations must be non-negative integer"
            )


@dataclass(frozen=True, slots=True)
class _EPAFace:
    a: int
    b: int
    c: int
    normal: Vec3
    distance: float

    @property
    def indices(self) -> tuple[int, int, int]:
        return (self.a, self.b, self.c)


def _validate_pair(a: RigidBody, b: RigidBody) -> None:
    if not isinstance(a, RigidBody) or not isinstance(b, RigidBody):
        raise PhysicsValidationError("convex query requires rigid bodies")
    if a.body_id == b.body_id:
        raise PhysicsValidationError(
            "convex query requires distinct rigid bodies"
        )
    if isinstance(a.shape, PlaneShape) or isinstance(b.shape, PlaneShape):
        raise PhysicsValidationError(
            "infinite planes are not finite convex support maps"
        )


def _safe_direction(direction: Vec3) -> Vec3:
    if not isinstance(direction, Vec3):
        raise PhysicsValidationError("convex support direction must be Vec3")
    if direction.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        return Vec3.axis(0)
    return direction


def support_vertex(
    a: RigidBody,
    b: RigidBody,
    direction: Vec3,
) -> SupportVertex:
    _validate_pair(a, b)
    direction = _safe_direction(direction)
    point_a = a.shape.support(direction, a.transform)
    point_b = b.shape.support(-direction, b.transform)
    return SupportVertex(
        point=point_a - point_b,
        point_a=point_a,
        point_b=point_b,
    )


def _triple_product(a: Vec3, b: Vec3, c: Vec3) -> Vec3:
    return a.cross(b).cross(c)


def _perpendicular(vector: Vec3) -> Vec3:
    if vector.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        return Vec3.axis(0)
    candidates = (Vec3.axis(0), Vec3.axis(1), Vec3.axis(2))
    helper = min(
        candidates,
        key=lambda axis: (
            abs(vector.dot(axis)),
            axis.to_tuple(),
        ),
    )
    result = vector.cross(helper)
    if result.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        result = vector.cross(Vec3.axis(2))
    return result.normalized()


def _line_simplex(
    simplex: list[SupportVertex],
) -> tuple[bool, Vec3]:
    a = simplex[0].point
    b = simplex[1].point
    ab = b - a
    ao = -a

    if ab.dot(ao) > 0.0:
        direction = _triple_product(ab, ao, ab)
        if direction.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
            direction = _perpendicular(ab)
        simplex[:] = (simplex[0], simplex[1])
        return False, direction

    simplex[:] = (simplex[0],)
    return False, _safe_direction(ao)


def _triangle_simplex(
    simplex: list[SupportVertex],
) -> tuple[bool, Vec3]:
    a_vertex, b_vertex, c_vertex = simplex[:3]
    a = a_vertex.point
    b = b_vertex.point
    c = c_vertex.point
    ab = b - a
    ac = c - a
    ao = -a
    abc = ab.cross(ac)

    if abc.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        # Degenerate triangle: keep the longest edge touching newest point.
        if ab.length_squared() >= ac.length_squared():
            simplex[:] = (a_vertex, b_vertex)
        else:
            simplex[:] = (a_vertex, c_vertex)
        return _line_simplex(simplex)

    outside_ac = abc.cross(ac)
    if outside_ac.dot(ao) > 0.0:
        if ac.dot(ao) > 0.0:
            simplex[:] = (a_vertex, c_vertex)
            direction = _triple_product(ac, ao, ac)
            if direction.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
                direction = _perpendicular(ac)
            return False, direction
        simplex[:] = (a_vertex, b_vertex)
        return _line_simplex(simplex)

    outside_ab = ab.cross(abc)
    if outside_ab.dot(ao) > 0.0:
        simplex[:] = (a_vertex, b_vertex)
        return _line_simplex(simplex)

    if abc.dot(ao) > 0.0:
        simplex[:] = (a_vertex, b_vertex, c_vertex)
        return False, abc

    simplex[:] = (a_vertex, c_vertex, b_vertex)
    return False, -abc


def _face_outward_normal(
    a: Vec3,
    b: Vec3,
    c: Vec3,
    opposite: Vec3,
) -> Vec3:
    normal = (b - a).cross(c - a)
    if normal.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        return Vec3.zero()
    if normal.dot(opposite - a) > 0.0:
        normal = -normal
    return normal


def _tetrahedron_simplex(
    simplex: list[SupportVertex],
) -> tuple[bool, Vec3]:
    a_vertex, b_vertex, c_vertex, d_vertex = simplex[:4]
    a = a_vertex.point
    b = b_vertex.point
    c = c_vertex.point
    d = d_vertex.point
    ao = -a

    faces = (
        (b_vertex, c_vertex, d_vertex, _face_outward_normal(a, b, c, d)),
        (c_vertex, d_vertex, b_vertex, _face_outward_normal(a, c, d, b)),
        (d_vertex, b_vertex, c_vertex, _face_outward_normal(a, d, b, c)),
    )

    for first, second, _opposite_vertex, normal in faces:
        if (
            normal.length_squared() > _GJK_DIRECTION_EPSILON_SQ
            and normal.dot(ao) > 0.0
        ):
            simplex[:] = (a_vertex, first, second)
            return _triangle_simplex(simplex)

    return True, Vec3.zero()


def _update_simplex(
    simplex: list[SupportVertex],
) -> tuple[bool, Vec3]:
    if len(simplex) == 1:
        direction = -simplex[0].point
        if direction.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
            return True, Vec3.zero()
        return False, direction
    if len(simplex) == 2:
        return _line_simplex(simplex)
    if len(simplex) == 3:
        return _triangle_simplex(simplex)
    if len(simplex) == 4:
        return _tetrahedron_simplex(simplex)
    raise ConvexQueryError("GJK simplex exceeded tetrahedron bound")


def _distance_segment(
    vertices: tuple[SupportVertex, SupportVertex],
) -> tuple[tuple[SupportVertex, ...], tuple[float, ...], Vec3]:
    first, second = vertices
    edge = second.point - first.point
    denominator = edge.length_squared()
    if denominator <= _GJK_DIRECTION_EPSILON_SQ:
        return (first,), (1.0,), first.point
    parameter = -first.point.dot(edge) / denominator
    if parameter <= 0.0:
        return (first,), (1.0,), first.point
    if parameter >= 1.0:
        return (second,), (1.0,), second.point
    closest = first.point + edge * parameter
    return (
        (first, second),
        (1.0 - parameter, parameter),
        closest,
    )


def _distance_triangle(
    vertices: tuple[SupportVertex, SupportVertex, SupportVertex],
) -> tuple[tuple[SupportVertex, ...], tuple[float, ...], Vec3]:
    a_vertex, b_vertex, c_vertex = vertices
    a = a_vertex.point
    b = b_vertex.point
    c = c_vertex.point
    ab = b - a
    ac = c - a
    ap = -a

    d1 = ab.dot(ap)
    d2 = ac.dot(ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return (a_vertex,), (1.0,), a

    bp = -b
    d3 = ab.dot(bp)
    d4 = ac.dot(bp)
    if d3 >= 0.0 and d4 <= d3:
        return (b_vertex,), (1.0,), b

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        denominator = d1 - d3
        if abs(denominator) <= EPSILON:
            return _distance_segment((a_vertex, b_vertex))
        v = d1 / denominator
        return (
            (a_vertex, b_vertex),
            (1.0 - v, v),
            a + ab * v,
        )

    cp = -c
    d5 = ab.dot(cp)
    d6 = ac.dot(cp)
    if d6 >= 0.0 and d5 <= d6:
        return (c_vertex,), (1.0,), c

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        denominator = d2 - d6
        if abs(denominator) <= EPSILON:
            return _distance_segment((a_vertex, c_vertex))
        w = d2 / denominator
        return (
            (a_vertex, c_vertex),
            (1.0 - w, w),
            a + ac * w,
        )

    va = d3 * d6 - d5 * d4
    if (
        va <= 0.0
        and (d4 - d3) >= 0.0
        and (d5 - d6) >= 0.0
    ):
        denominator = (d4 - d3) + (d5 - d6)
        if abs(denominator) <= EPSILON:
            return _distance_segment((b_vertex, c_vertex))
        w = (d4 - d3) / denominator
        return (
            (b_vertex, c_vertex),
            (1.0 - w, w),
            b + (c - b) * w,
        )

    denominator = va + vb + vc
    if abs(denominator) <= 1.0e-20:
        candidates = (
            _distance_segment((a_vertex, b_vertex)),
            _distance_segment((a_vertex, c_vertex)),
            _distance_segment((b_vertex, c_vertex)),
        )
        return min(
            candidates,
            key=lambda row: (
                row[2].length_squared(),
                tuple(vertex.point.to_tuple() for vertex in row[0]),
            ),
        )

    inverse = 1.0 / denominator
    v = vb * inverse
    w = vc * inverse
    u = 1.0 - v - w
    closest = a * u + b * v + c * w
    return vertices, (u, v, w), closest


def _origin_inside_tetrahedron(
    vertices: tuple[
        SupportVertex,
        SupportVertex,
        SupportVertex,
        SupportVertex,
    ],
) -> bool:
    points = tuple(vertex.point for vertex in vertices)
    faces = (
        (0, 1, 2, 3),
        (0, 3, 1, 2),
        (0, 2, 3, 1),
        (1, 3, 2, 0),
    )
    valid_faces = 0
    for i, j, k, opposite in faces:
        a, b, d = points[i], points[j], points[k]
        normal = (b - a).cross(d - a)
        if normal.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
            continue
        valid_faces += 1
        origin_side = normal.dot(-a)
        opposite_side = normal.dot(points[opposite] - a)
        if origin_side * opposite_side < -1.0e-18:
            return False
    return valid_faces == 4


def _distance_tetrahedron(
    vertices: tuple[
        SupportVertex,
        SupportVertex,
        SupportVertex,
        SupportVertex,
    ],
) -> tuple[
    tuple[SupportVertex, ...],
    tuple[float, ...],
    Vec3,
    bool,
]:
    if _origin_inside_tetrahedron(vertices):
        return vertices, (0.25, 0.25, 0.25, 0.25), Vec3.zero(), True

    faces = (
        (0, 1, 2),
        (0, 3, 1),
        (0, 2, 3),
        (1, 3, 2),
    )
    candidates = []
    for face in faces:
        reduced, weights, closest = _distance_triangle(
            tuple(vertices[index] for index in face)  # type: ignore[arg-type]
        )
        candidates.append((reduced, weights, closest))
    reduced, weights, closest = min(
        candidates,
        key=lambda row: (
            row[2].length_squared(),
            tuple(vertex.point.to_tuple() for vertex in row[0]),
        ),
    )
    return reduced, weights, closest, False


def _reduce_distance_simplex(
    simplex: tuple[SupportVertex, ...],
) -> tuple[
    tuple[SupportVertex, ...],
    tuple[float, ...],
    Vec3,
    bool,
]:
    if len(simplex) == 1:
        return simplex, (1.0,), simplex[0].point, False
    if len(simplex) == 2:
        reduced, weights, closest = _distance_segment(
            (simplex[0], simplex[1])
        )
        return reduced, weights, closest, False
    if len(simplex) == 3:
        reduced, weights, closest = _distance_triangle(
            (simplex[0], simplex[1], simplex[2])
        )
        return reduced, weights, closest, False
    if len(simplex) == 4:
        return _distance_tetrahedron(
            (simplex[0], simplex[1], simplex[2], simplex[3])
        )
    raise ConvexQueryError("GJK distance simplex exceeded tetrahedron bound")


def _distance_result(
    simplex: tuple[SupportVertex, ...],
    weights: tuple[float, ...],
    closest: Vec3,
    *,
    iterations: int,
    intersects: bool,
) -> GJKDistanceResult:
    point_a = Vec3.zero()
    point_b = Vec3.zero()
    for weight, vertex in zip(weights, simplex):
        point_a = point_a + vertex.point_a * weight
        point_b = point_b + vertex.point_b * weight

    separation = point_b - point_a
    distance = 0.0 if intersects else separation.length()
    normal = (
        Vec3.zero()
        if distance <= 1.0e-12
        else separation / distance
    )
    return GJKDistanceResult(
        intersects=intersects,
        distance=distance,
        normal=normal,
        point_a=point_a,
        point_b=point_b,
        iterations=iterations,
        simplex=simplex,
        weights=weights,
    )


def gjk_distance(
    a: RigidBody,
    b: RigidBody,
    *,
    max_iterations: int = 64,
    tolerance: float = 1.0e-9,
) -> GJKDistanceResult:
    """Closest witnesses for two finite convex support maps.

    normal points from shape A toward shape B for separated shapes.
    Intersections return distance zero and a zero normal; EPA remains the
    penetration-normal authority.
    """

    _validate_pair(a, b)
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or not 1 <= max_iterations <= MAX_GJK_ITERATIONS
    ):
        raise PhysicsValidationError(
            "GJK distance max_iterations outside supported range"
        )
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(float(tolerance))
        or float(tolerance) <= 0.0
    ):
        raise PhysicsValidationError(
            "GJK distance tolerance must be positive"
        )
    tolerance = float(tolerance)

    direction = b.position - a.position
    if direction.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        direction = Vec3.axis(0)

    simplex = (support_vertex(a, b, direction),)
    simplex, weights, closest, intersects = _reduce_distance_simplex(simplex)
    if intersects or closest.length_squared() <= tolerance * tolerance:
        return _distance_result(
            simplex,
            weights,
            Vec3.zero(),
            iterations=0,
            intersects=True,
        )

    previous_distance_sq = closest.length_squared()
    for iteration in range(1, max_iterations + 1):
        search = -closest
        candidate = support_vertex(a, b, search)

        if any(
            (candidate.point - existing.point).length_squared()
            <= _DUPLICATE_SUPPORT_EPSILON_SQ
            for existing in simplex
        ):
            return _distance_result(
                simplex,
                weights,
                closest,
                iterations=iteration,
                intersects=False,
            )

        improvement = (
            closest.length_squared()
            - closest.dot(candidate.point)
        )
        if improvement <= tolerance * max(
            1.0,
            closest.length_squared(),
        ):
            return _distance_result(
                simplex,
                weights,
                closest,
                iterations=iteration,
                intersects=False,
            )

        expanded = simplex + (candidate,)
        simplex, weights, closest, intersects = _reduce_distance_simplex(
            expanded
        )
        if intersects or closest.length_squared() <= tolerance * tolerance:
            return _distance_result(
                simplex,
                weights,
                Vec3.zero(),
                iterations=iteration,
                intersects=True,
            )

        current_distance_sq = closest.length_squared()
        if (
            previous_distance_sq - current_distance_sq
            <= tolerance * max(1.0, previous_distance_sq)
        ):
            return _distance_result(
                simplex,
                weights,
                closest,
                iterations=iteration,
                intersects=False,
            )
        previous_distance_sq = current_distance_sq

    raise ConvexQueryError("GJK distance iteration bound exceeded")


def gjk_intersection(
    a: RigidBody,
    b: RigidBody,
    *,
    max_iterations: int = 64,
    tolerance: float = 1.0e-10,
) -> GJKResult:
    _validate_pair(a, b)
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or not 1 <= max_iterations <= MAX_GJK_ITERATIONS
    ):
        raise PhysicsValidationError(
            "GJK max_iterations outside supported range"
        )
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(float(tolerance))
        or float(tolerance) <= 0.0
    ):
        raise PhysicsValidationError("GJK tolerance must be positive")
    tolerance = float(tolerance)

    direction = b.position - a.position
    if direction.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        direction = Vec3.axis(0)

    first = support_vertex(a, b, direction)
    simplex = [first]
    direction = -first.point
    if direction.length_squared() <= tolerance * tolerance:
        return GJKResult(True, 0, tuple(simplex), Vec3.zero())

    for iteration in range(1, max_iterations + 1):
        candidate = support_vertex(a, b, direction)
        projection = candidate.point.dot(direction)
        if projection < -tolerance:
            return GJKResult(
                False,
                iteration,
                tuple(simplex),
                direction,
            )

        if any(
            (candidate.point - existing.point).length_squared()
            <= _DUPLICATE_SUPPORT_EPSILON_SQ
            for existing in simplex
        ):
            # No new extreme point. If the current simplex has not enclosed the
            # origin, the bounded search has converged to a separating feature.
            return GJKResult(
                False,
                iteration,
                tuple(simplex),
                direction,
            )

        simplex.insert(0, candidate)
        contains_origin, direction = _update_simplex(simplex)
        if contains_origin:
            return GJKResult(
                True,
                iteration,
                tuple(simplex),
                Vec3.zero(),
            )
        if direction.length_squared() <= tolerance * tolerance:
            return GJKResult(
                True,
                iteration,
                tuple(simplex),
                Vec3.zero(),
            )

    raise ConvexQueryError("GJK iteration bound exceeded")


def _make_epa_face(
    vertices: list[SupportVertex],
    a: int,
    b: int,
    c: int,
) -> _EPAFace | None:
    first = vertices[a].point
    second = vertices[b].point
    third = vertices[c].point
    normal = (second - first).cross(third - first)
    if normal.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        return None
    normal = normal.normalized()
    distance = normal.dot(first)
    if distance < 0.0:
        b, c = c, b
        normal = -normal
        distance = -distance
    return _EPAFace(a, b, c, normal, max(0.0, distance))


def _barycentric_triangle(
    point: Vec3,
    a: Vec3,
    b: Vec3,
    c: Vec3,
) -> tuple[float, float, float]:
    v0 = b - a
    v1 = c - a
    v2 = point - a
    d00 = v0.dot(v0)
    d01 = v0.dot(v1)
    d11 = v1.dot(v1)
    d20 = v2.dot(v0)
    d21 = v2.dot(v1)
    denominator = d00 * d11 - d01 * d01
    if abs(denominator) <= 1.0e-20:
        raise ConvexQueryError("EPA witness triangle is degenerate")
    inverse = 1.0 / denominator
    v = (d11 * d20 - d01 * d21) * inverse
    w = (d00 * d21 - d01 * d20) * inverse
    u = 1.0 - v - w

    values = [max(0.0, u), max(0.0, v), max(0.0, w)]
    total = sum(values)
    if total <= EPSILON:
        raise ConvexQueryError("EPA witness barycentric weights collapsed")
    return tuple(value / total for value in values)  # type: ignore[return-value]


def _epa_witness(
    vertices: list[SupportVertex],
    face: _EPAFace,
    *,
    iterations: int,
) -> EPAPenetration:
    support = (
        vertices[face.a],
        vertices[face.b],
        vertices[face.c],
    )
    projected = face.normal * face.distance
    weights = _barycentric_triangle(
        projected,
        support[0].point,
        support[1].point,
        support[2].point,
    )

    point_a = Vec3.zero()
    point_b = Vec3.zero()
    for weight, vertex in zip(weights, support):
        point_a = point_a + vertex.point_a * weight
        point_b = point_b + vertex.point_b * weight

    return EPAPenetration(
        normal=face.normal,
        depth=face.distance,
        point_a=point_a,
        point_b=point_b,
        contact_point=(point_a + point_b) * 0.5,
        iterations=iterations,
    )


def _initial_epa_faces(
    vertices: list[SupportVertex],
) -> list[_EPAFace]:
    if len(vertices) != 4:
        raise ConvexQueryError(
            "EPA requires tetrahedral GJK simplex"
        )
    candidates = (
        (0, 1, 2),
        (0, 3, 1),
        (0, 2, 3),
        (1, 3, 2),
    )
    faces = [
        face
        for indices in candidates
        if (face := _make_epa_face(vertices, *indices)) is not None
    ]
    if len(faces) < 4:
        raise ConvexQueryError("EPA initial simplex is degenerate")
    return faces


def epa_penetration(
    a: RigidBody,
    b: RigidBody,
    gjk: GJKResult | None = None,
    *,
    max_iterations: int = 64,
    tolerance: float = 1.0e-7,
) -> EPAPenetration | None:
    _validate_pair(a, b)
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or not 1 <= max_iterations <= MAX_EPA_ITERATIONS
    ):
        raise PhysicsValidationError(
            "EPA max_iterations outside supported range"
        )
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(float(tolerance))
        or float(tolerance) <= 0.0
    ):
        raise PhysicsValidationError("EPA tolerance must be positive")
    tolerance = float(tolerance)

    result = gjk if gjk is not None else gjk_intersection(a, b)
    if not isinstance(result, GJKResult):
        raise PhysicsValidationError("EPA requires GJKResult")
    if not result.intersects:
        return None
    if len(result.simplex) != 4:
        raise ConvexQueryError(
            "EPA cannot expand non-tetrahedral touching simplex"
        )

    vertices = list(result.simplex)
    faces = _initial_epa_faces(vertices)

    for iteration in range(1, max_iterations + 1):
        face = min(
            faces,
            key=lambda row: (
                row.distance,
                row.a,
                row.b,
                row.c,
            ),
        )
        candidate = support_vertex(a, b, face.normal)
        projection = candidate.point.dot(face.normal)

        if projection - face.distance <= tolerance:
            return _epa_witness(
                vertices,
                face,
                iterations=iteration,
            )

        duplicate = any(
            (candidate.point - vertex.point).length_squared()
            <= _DUPLICATE_SUPPORT_EPSILON_SQ
            for vertex in vertices
        )
        if duplicate:
            return _epa_witness(
                vertices,
                face,
                iterations=iteration,
            )

        if len(vertices) >= MAX_EPA_VERTICES:
            raise ConvexQueryError("EPA vertex bound exceeded")
        new_index = len(vertices)
        vertices.append(candidate)

        visible: list[_EPAFace] = []
        for existing in faces:
            anchor = vertices[existing.a].point
            if existing.normal.dot(candidate.point - anchor) > tolerance:
                visible.append(existing)

        if not visible:
            return _epa_witness(
                vertices,
                face,
                iterations=iteration,
            )

        boundary: list[tuple[int, int]] = []
        for visible_face in visible:
            for edge in (
                (visible_face.a, visible_face.b),
                (visible_face.b, visible_face.c),
                (visible_face.c, visible_face.a),
            ):
                reverse = (edge[1], edge[0])
                if reverse in boundary:
                    boundary.remove(reverse)
                else:
                    boundary.append(edge)

        visible_set = set(visible)
        faces = [face_row for face_row in faces if face_row not in visible_set]

        for edge in sorted(boundary):
            new_face = _make_epa_face(
                vertices,
                edge[0],
                edge[1],
                new_index,
            )
            if new_face is not None:
                faces.append(new_face)
            if len(faces) > MAX_EPA_FACES:
                raise ConvexQueryError("EPA face bound exceeded")

        if not faces:
            raise ConvexQueryError("EPA polytope lost all faces")

    raise ConvexQueryError("EPA iteration bound exceeded")


def convex_penetration(
    a: RigidBody,
    b: RigidBody,
    *,
    gjk_iterations: int = 64,
    epa_iterations: int = 64,
    tolerance: float = 1.0e-7,
) -> EPAPenetration | None:
    result = gjk_intersection(
        a,
        b,
        max_iterations=gjk_iterations,
        tolerance=min(tolerance, 1.0e-10),
    )
    if not result.intersects:
        return None
    return epa_penetration(
        a,
        b,
        result,
        max_iterations=epa_iterations,
        tolerance=tolerance,
    )
