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
from .math3d import EPSILON, Mat3, Quat, Transform, Vec3
from .shapes import (
    BoxShape,
    CapsuleShape,
    ConvexHullShape,
    CylinderShape,
    PlaneShape,
    SphereShape,
)

MAX_GJK_ITERATIONS = 128
MAX_EPA_ITERATIONS = 128
MAX_EPA_VERTICES = 256
MAX_EPA_FACES = 512
MAX_CONVEX_TOI_ITERATIONS = 128
MAX_CONVEX_TOI_FALLBACK_SAMPLES = 256
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
class ConvexDistanceResult:
    intersects: bool
    distance: float
    normal: Vec3
    point_a: Vec3
    point_b: Vec3
    iterations: int
    simplex_size: int

    def __post_init__(self) -> None:
        if not isinstance(self.intersects, bool):
            raise PhysicsValidationError("convex distance intersects must be boolean")
        if (
            isinstance(self.distance, bool)
            or not isinstance(self.distance, (int, float))
            or not math.isfinite(float(self.distance))
            or float(self.distance) < 0.0
        ):
            raise PhysicsValidationError(
                "convex distance must be finite and non-negative"
            )
        object.__setattr__(self, "distance", float(self.distance))
        object.__setattr__(self, "normal", self.normal.normalized())
        if not isinstance(self.point_a, Vec3) or not isinstance(self.point_b, Vec3):
            raise PhysicsValidationError("convex distance witnesses must be Vec3")
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 0
        ):
            raise PhysicsValidationError(
                "convex distance iterations must be non-negative integer"
            )
        if (
            isinstance(self.simplex_size, bool)
            or not isinstance(self.simplex_size, int)
            or not 1 <= self.simplex_size <= 4
        ):
            raise PhysicsValidationError(
                "convex distance simplex_size outside [1, 4]"
            )


@dataclass(frozen=True, slots=True)
class ConvexTOIResult:
    body_a: str
    body_b: str
    fraction: float
    time: float
    normal: Vec3
    point_a: Vec3
    point_b: Vec3
    iterations: int
    initial_overlap: bool = False

    def __post_init__(self) -> None:
        if not self.body_a or not self.body_b or self.body_a == self.body_b:
            raise PhysicsValidationError("convex TOI requires distinct body ids")
        if not math.isfinite(self.fraction) or not 0.0 <= self.fraction <= 1.0:
            raise PhysicsValidationError("convex TOI fraction must be in [0, 1]")
        if not math.isfinite(self.time) or self.time < 0.0:
            raise PhysicsValidationError("convex TOI time must be non-negative")
        object.__setattr__(self, "normal", self.normal.normalized())
        if not isinstance(self.point_a, Vec3) or not isinstance(self.point_b, Vec3):
            raise PhysicsValidationError("convex TOI witnesses must be Vec3")
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 0
        ):
            raise PhysicsValidationError(
                "convex TOI iterations must be non-negative integer"
            )
        if not isinstance(self.initial_overlap, bool):
            raise PhysicsValidationError(
                "convex TOI initial_overlap must be boolean"
            )


@dataclass(frozen=True, slots=True)
class _ClosestSimplex:
    vertices: tuple[SupportVertex, ...]
    weights: tuple[float, ...]
    point: Vec3
    contains_origin: bool = False


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


def _support_vertex_transforms(
    a: RigidBody,
    b: RigidBody,
    direction: Vec3,
    transform_a: Transform,
    transform_b: Transform,
) -> SupportVertex:
    _validate_pair(a, b)
    if not isinstance(transform_a, Transform) or not isinstance(transform_b, Transform):
        raise PhysicsValidationError("convex support transforms must be Transform")
    direction = _safe_direction(direction)
    point_a = a.shape.support(direction, transform_a)
    point_b = b.shape.support(-direction, transform_b)
    return SupportVertex(
        point=point_a - point_b,
        point_a=point_a,
        point_b=point_b,
    )


def _weighted_point(
    vertices: tuple[SupportVertex, ...],
    weights: tuple[float, ...],
    *,
    witness: str,
) -> Vec3:
    result = Vec3.zero()
    for vertex, weight in zip(vertices, weights):
        source = vertex.point_a if witness == "a" else vertex.point_b
        result = result + source * weight
    return result


def _reduce_closest(
    vertices: tuple[SupportVertex, ...],
    weights: tuple[float, ...],
    point: Vec3,
    *,
    contains_origin: bool = False,
) -> _ClosestSimplex:
    pairs = [
        (vertex, max(0.0, weight))
        for vertex, weight in zip(vertices, weights)
        if weight > 1.0e-12
    ]
    if not pairs:
        index = min(
            range(len(vertices)),
            key=lambda item: (
                vertices[item].point.length_squared(),
                item,
            ),
        )
        return _ClosestSimplex(
            (vertices[index],),
            (1.0,),
            vertices[index].point,
            contains_origin=False,
        )
    total = sum(weight for _, weight in pairs)
    reduced_vertices = tuple(vertex for vertex, _ in pairs)
    reduced_weights = tuple(weight / total for _, weight in pairs)
    reduced_point = Vec3.zero()
    for vertex, weight in zip(reduced_vertices, reduced_weights):
        reduced_point = reduced_point + vertex.point * weight
    return _ClosestSimplex(
        reduced_vertices,
        reduced_weights,
        Vec3.zero() if contains_origin else reduced_point,
        contains_origin=contains_origin,
    )


def _closest_segment_origin(
    first: SupportVertex,
    second: SupportVertex,
) -> _ClosestSimplex:
    a = first.point
    b = second.point
    direction = b - a
    denominator = direction.length_squared()
    if denominator <= _GJK_DIRECTION_EPSILON_SQ:
        chosen = min(
            (first, second),
            key=lambda row: row.point.length_squared(),
        )
        return _ClosestSimplex((chosen,), (1.0,), chosen.point)
    t = min(1.0, max(0.0, -a.dot(direction) / denominator))
    point = a + direction * t
    return _reduce_closest(
        (first, second),
        (1.0 - t, t),
        point,
    )


def _closest_triangle_origin(
    first: SupportVertex,
    second: SupportVertex,
    third: SupportVertex,
) -> _ClosestSimplex:
    a = first.point
    b = second.point
    c = third.point
    ab = b - a
    ac = c - a
    ap = -a
    d1 = ab.dot(ap)
    d2 = ac.dot(ap)
    if d1 <= 0.0 and d2 <= 0.0:
        return _ClosestSimplex((first,), (1.0,), a)

    bp = -b
    d3 = ab.dot(bp)
    d4 = ac.dot(bp)
    if d3 >= 0.0 and d4 <= d3:
        return _ClosestSimplex((second,), (1.0,), b)

    vc = d1 * d4 - d3 * d2
    if vc <= 0.0 and d1 >= 0.0 and d3 <= 0.0:
        denominator = d1 - d3
        if abs(denominator) <= _GJK_DIRECTION_EPSILON_SQ:
            return _closest_segment_origin(first, second)
        v = d1 / denominator
        return _reduce_closest(
            (first, second),
            (1.0 - v, v),
            a + ab * v,
        )

    cp = -c
    d5 = ab.dot(cp)
    d6 = ac.dot(cp)
    if d6 >= 0.0 and d5 <= d6:
        return _ClosestSimplex((third,), (1.0,), c)

    vb = d5 * d2 - d1 * d6
    if vb <= 0.0 and d2 >= 0.0 and d6 <= 0.0:
        denominator = d2 - d6
        if abs(denominator) <= _GJK_DIRECTION_EPSILON_SQ:
            return _closest_segment_origin(first, third)
        w = d2 / denominator
        return _reduce_closest(
            (first, third),
            (1.0 - w, w),
            a + ac * w,
        )

    va = d3 * d6 - d5 * d4
    edge_bc_a = d4 - d3
    edge_bc_b = d5 - d6
    if va <= 0.0 and edge_bc_a >= 0.0 and edge_bc_b >= 0.0:
        denominator = edge_bc_a + edge_bc_b
        if abs(denominator) <= _GJK_DIRECTION_EPSILON_SQ:
            return _closest_segment_origin(second, third)
        w = edge_bc_a / denominator
        return _reduce_closest(
            (second, third),
            (1.0 - w, w),
            b + (c - b) * w,
        )

    denominator = va + vb + vc
    if abs(denominator) <= _GJK_DIRECTION_EPSILON_SQ:
        candidates = (
            _closest_segment_origin(first, second),
            _closest_segment_origin(first, third),
            _closest_segment_origin(second, third),
        )
        return min(
            candidates,
            key=lambda row: row.point.length_squared(),
        )
    inverse = 1.0 / denominator
    v = vb * inverse
    w = vc * inverse
    u = 1.0 - v - w
    return _reduce_closest(
        (first, second, third),
        (u, v, w),
        a * u + b * v + c * w,
    )


def _closest_tetrahedron_origin(
    vertices: tuple[SupportVertex, SupportVertex, SupportVertex, SupportVertex],
) -> _ClosestSimplex:
    a, b, c, d = (row.point for row in vertices)
    matrix = Mat3.from_columns(b - a, c - a, d - a)

    if matrix.is_invertible():
        coordinates = matrix.inverse().mul_vec(-a)
        weights = (
            1.0 - coordinates.x - coordinates.y - coordinates.z,
            coordinates.x,
            coordinates.y,
            coordinates.z,
        )
        if min(weights) >= -1.0e-10 and max(weights) <= 1.0 + 1.0e-10:
            clamped = tuple(max(0.0, value) for value in weights)
            total = sum(clamped)
            normalized = tuple(value / total for value in clamped)
            return _reduce_closest(
                vertices,
                normalized,
                Vec3.zero(),
                contains_origin=True,
            )

    face_indices = (
        (0, 1, 2),
        (0, 1, 3),
        (0, 2, 3),
        (1, 2, 3),
    )
    candidates = tuple(
        _closest_triangle_origin(
            vertices[i],
            vertices[j],
            vertices[k],
        )
        for i, j, k in face_indices
    )
    return min(
        enumerate(candidates),
        key=lambda row: (
            row[1].point.length_squared(),
            row[0],
        ),
    )[1]


def _closest_simplex_origin(
    simplex: tuple[SupportVertex, ...],
) -> _ClosestSimplex:
    if len(simplex) == 1:
        return _ClosestSimplex(simplex, (1.0,), simplex[0].point)
    if len(simplex) == 2:
        return _closest_segment_origin(simplex[0], simplex[1])
    if len(simplex) == 3:
        return _closest_triangle_origin(simplex[0], simplex[1], simplex[2])
    if len(simplex) == 4:
        return _closest_tetrahedron_origin(
            (simplex[0], simplex[1], simplex[2], simplex[3])
        )
    raise ConvexQueryError("convex distance simplex outside tetrahedron bound")


def _distance_result_from_closest(
    closest: _ClosestSimplex,
    *,
    iterations: int,
    transform_a: Transform,
    transform_b: Transform,
    tolerance: float,
) -> ConvexDistanceResult:
    point_a = _weighted_point(
        closest.vertices,
        closest.weights,
        witness="a",
    )
    point_b = _weighted_point(
        closest.vertices,
        closest.weights,
        witness="b",
    )
    witness_delta = point_b - point_a
    witness_distance = witness_delta.length()
    intersects = closest.contains_origin or witness_distance <= tolerance
    if witness_distance > tolerance:
        normal = witness_delta / witness_distance
        distance = witness_distance
    else:
        center_delta = transform_b.position - transform_a.position
        normal = center_delta.normalized_or_zero()
        if normal.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
            normal = Vec3.axis(0)
        distance = 0.0
    return ConvexDistanceResult(
        intersects=intersects,
        distance=distance,
        normal=normal,
        point_a=point_a,
        point_b=point_b,
        iterations=iterations,
        simplex_size=len(closest.vertices),
    )


def _convex_distance_transforms(
    a: RigidBody,
    b: RigidBody,
    transform_a: Transform,
    transform_b: Transform,
    *,
    max_iterations: int,
    tolerance: float,
) -> ConvexDistanceResult:
    direction = transform_b.position - transform_a.position
    if direction.length_squared() <= _GJK_DIRECTION_EPSILON_SQ:
        direction = Vec3.axis(0)

    first = _support_vertex_transforms(
        a,
        b,
        direction,
        transform_a,
        transform_b,
    )
    closest = _closest_simplex_origin((first,))

    for iteration in range(1, max_iterations + 1):
        distance_sq = closest.point.length_squared()
        if closest.contains_origin or distance_sq <= tolerance * tolerance:
            return _distance_result_from_closest(
                closest,
                iterations=iteration - 1,
                transform_a=transform_a,
                transform_b=transform_b,
                tolerance=tolerance,
            )

        direction = -closest.point
        candidate = _support_vertex_transforms(
            a,
            b,
            direction,
            transform_a,
            transform_b,
        )
        distance = math.sqrt(distance_sq)
        improvement = candidate.point.dot(direction) + distance_sq
        if improvement <= tolerance * max(1.0, distance):
            return _distance_result_from_closest(
                closest,
                iterations=iteration,
                transform_a=transform_a,
                transform_b=transform_b,
                tolerance=tolerance,
            )

        if any(
            (candidate.point - vertex.point).length_squared()
            <= _DUPLICATE_SUPPORT_EPSILON_SQ
            for vertex in closest.vertices
        ):
            return _distance_result_from_closest(
                closest,
                iterations=iteration,
                transform_a=transform_a,
                transform_b=transform_b,
                tolerance=tolerance,
            )

        trial = closest.vertices + (candidate,)
        if len(trial) > 4:
            raise ConvexQueryError(
                "convex distance simplex exceeded tetrahedron bound"
            )
        closest = _closest_simplex_origin(trial)

    raise ConvexQueryError("convex distance iteration bound exceeded")


def convex_distance(
    a: RigidBody,
    b: RigidBody,
    *,
    max_iterations: int = 64,
    tolerance: float = 1.0e-9,
) -> ConvexDistanceResult:
    _validate_pair(a, b)
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or not 1 <= max_iterations <= MAX_GJK_ITERATIONS
    ):
        raise PhysicsValidationError(
            "convex distance max_iterations outside supported range"
        )
    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(float(tolerance))
        or float(tolerance) <= 0.0
    ):
        raise PhysicsValidationError(
            "convex distance tolerance must be positive"
        )
    return _convex_distance_transforms(
        a,
        b,
        a.transform,
        b.transform,
        max_iterations=max_iterations,
        tolerance=float(tolerance),
    )


def _predicted_transform(body: RigidBody, time: float) -> Transform:
    position = body.position + body.linear_velocity * time
    angular_speed = body.angular_velocity.length()
    if angular_speed <= 1.0e-12 or time <= 0.0:
        rotation = body.orientation
    else:
        axis = body.angular_velocity / angular_speed
        delta = Quat.from_axis_angle(axis, angular_speed * time)
        rotation = (delta * body.orientation).normalized()
    return Transform(position=position, rotation=rotation)


def _shape_sweep_radius(body: RigidBody) -> float:
    shape = body.shape
    if isinstance(shape, SphereShape):
        return shape.radius
    if isinstance(shape, BoxShape):
        return shape.half_extents.length()
    if isinstance(shape, CapsuleShape):
        return shape.half_height + shape.radius
    if isinstance(shape, CylinderShape):
        return math.hypot(shape.radius, shape.half_height)
    if isinstance(shape, ConvexHullShape):
        return max(vertex.length() for vertex in shape.vertices)
    raise PhysicsValidationError(
        "convex TOI requires finite supported shape"
    )


def _distance_at_time(
    a: RigidBody,
    b: RigidBody,
    time: float,
    *,
    max_iterations: int,
    tolerance: float,
) -> ConvexDistanceResult:
    return _convex_distance_transforms(
        a,
        b,
        _predicted_transform(a, time),
        _predicted_transform(b, time),
        max_iterations=max_iterations,
        tolerance=tolerance,
    )


def _refine_convex_toi(
    a: RigidBody,
    b: RigidBody,
    low: float,
    high: float,
    *,
    distance_tolerance: float,
    time_tolerance: float,
    distance_iterations: int,
) -> tuple[float, ConvexDistanceResult]:
    result = _distance_at_time(
        a,
        b,
        high,
        max_iterations=distance_iterations,
        tolerance=distance_tolerance * 0.1,
    )
    for _ in range(48):
        if high - low <= time_tolerance:
            break
        middle = (low + high) * 0.5
        candidate = _distance_at_time(
            a,
            b,
            middle,
            max_iterations=distance_iterations,
            tolerance=distance_tolerance * 0.1,
        )
        if candidate.intersects or candidate.distance <= distance_tolerance:
            high = middle
            result = candidate
        else:
            low = middle
    return high, result


def _fallback_convex_toi_scan(
    a: RigidBody,
    b: RigidBody,
    start_time: float,
    dt: float,
    *,
    distance_tolerance: float,
    time_tolerance: float,
    distance_iterations: int,
) -> tuple[float, ConvexDistanceResult, int] | None:
    """Deterministically bracket contact after advancement stalls.

    Conservative advancement normally converges much faster than this path.
    The fallback exists for pathological witness-normal changes near curved
    features.  It never invents a collision: a scan sample must actually
    intersect or lie within the configured distance tolerance before binary
    refinement is allowed to return a TOI.
    """

    if start_time >= dt - time_tolerance:
        return None

    low = start_time
    span = dt - start_time
    for sample_index in range(1, MAX_CONVEX_TOI_FALLBACK_SAMPLES + 1):
        high = start_time + span * (
            sample_index / MAX_CONVEX_TOI_FALLBACK_SAMPLES
        )
        candidate = _distance_at_time(
            a,
            b,
            high,
            max_iterations=distance_iterations,
            tolerance=distance_tolerance * 0.1,
        )
        if candidate.intersects or candidate.distance <= distance_tolerance:
            refined_time, refined = _refine_convex_toi(
                a,
                b,
                low,
                high,
                distance_tolerance=distance_tolerance,
                time_tolerance=time_tolerance,
                distance_iterations=distance_iterations,
            )
            return refined_time, refined, sample_index
        low = high

    return None


def convex_time_of_impact(
    a: RigidBody,
    b: RigidBody,
    dt: float,
    *,
    max_iterations: int = 32,
    distance_iterations: int = 64,
    distance_tolerance: float = 1.0e-6,
    time_tolerance: float = 1.0e-9,
) -> ConvexTOIResult | None:
    _validate_pair(a, b)
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise PhysicsValidationError("convex TOI dt must be numeric")
    dt = float(dt)
    if not math.isfinite(dt) or dt <= 0.0:
        raise PhysicsValidationError("convex TOI dt must be positive")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or not 1 <= max_iterations <= MAX_CONVEX_TOI_ITERATIONS
    ):
        raise PhysicsValidationError(
            "convex TOI max_iterations outside supported range"
        )
    if (
        isinstance(distance_iterations, bool)
        or not isinstance(distance_iterations, int)
        or not 1 <= distance_iterations <= MAX_GJK_ITERATIONS
    ):
        raise PhysicsValidationError(
            "convex TOI distance_iterations outside supported range"
        )
    for name, value in (
        ("distance_tolerance", distance_tolerance),
        ("time_tolerance", time_tolerance),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise PhysicsValidationError(f"{name} must be positive")
    distance_tolerance = float(distance_tolerance)
    time_tolerance = float(time_tolerance)

    radius_a = _shape_sweep_radius(a)
    radius_b = _shape_sweep_radius(b)
    relative_velocity = b.linear_velocity - a.linear_velocity
    angular_bound = (
        a.angular_velocity.length() * radius_a
        + b.angular_velocity.length() * radius_b
    )

    time = 0.0
    previous_separated_time = 0.0

    for iteration in range(1, max_iterations + 1):
        result = _distance_at_time(
            a,
            b,
            time,
            max_iterations=distance_iterations,
            tolerance=distance_tolerance * 0.1,
        )

        if result.intersects or result.distance <= distance_tolerance:
            if time > 0.0:
                time, result = _refine_convex_toi(
                    a,
                    b,
                    previous_separated_time,
                    time,
                    distance_tolerance=distance_tolerance,
                    time_tolerance=time_tolerance,
                    distance_iterations=distance_iterations,
                )
            return ConvexTOIResult(
                body_a=a.body_id,
                body_b=b.body_id,
                fraction=min(1.0, max(0.0, time / dt)),
                time=time,
                normal=result.normal,
                point_a=result.point_a,
                point_b=result.point_b,
                iterations=iteration,
                initial_overlap=time <= time_tolerance,
            )

        # The signed linear term must remain inside the conservative
        # rotational bound.  A body translating away from the witness normal
        # can dominate the maximum possible angular approach rate; clipping
        # the linear term to zero first would invent closing speed and can
        # stall conservative advancement after a resolved impact.
        closing_bound = max(
            0.0,
            -relative_velocity.dot(result.normal) + angular_bound,
        )
        if closing_bound <= EPSILON:
            return None

        advance = (
            result.distance - distance_tolerance
        ) / closing_bound
        if advance <= 0.0:
            advance = time_tolerance

        previous_separated_time = time
        next_time = time + max(advance, time_tolerance)
        if next_time > dt + time_tolerance:
            return None
        time = min(dt, next_time)

    fallback = _fallback_convex_toi_scan(
        a,
        b,
        time,
        dt,
        distance_tolerance=distance_tolerance,
        time_tolerance=time_tolerance,
        distance_iterations=distance_iterations,
    )
    if fallback is None:
        return None

    fallback_time, result, scan_samples = fallback
    return ConvexTOIResult(
        body_a=a.body_id,
        body_b=b.body_id,
        fraction=min(1.0, max(0.0, fallback_time / dt)),
        time=fallback_time,
        normal=result.normal,
        point_a=result.point_a,
        point_b=result.point_b,
        iterations=max_iterations + scan_samples,
        initial_overlap=fallback_time <= time_tolerance,
    )


def _validate_convex_plane_pair(
    convex: RigidBody,
    plane: RigidBody,
) -> None:
    if not isinstance(convex, RigidBody) or not isinstance(plane, RigidBody):
        raise PhysicsValidationError(
            "convex-plane TOI requires rigid bodies"
        )
    if convex.body_id == plane.body_id:
        raise PhysicsValidationError(
            "convex-plane TOI requires distinct bodies"
        )
    if isinstance(convex.shape, PlaneShape):
        raise PhysicsValidationError(
            "convex-plane TOI requires finite convex first body"
        )
    if not isinstance(
        convex.shape,
        (
            SphereShape,
            BoxShape,
            CapsuleShape,
            CylinderShape,
            ConvexHullShape,
        ),
    ):
        raise PhysicsValidationError(
            "convex-plane TOI requires supported finite convex shape"
        )
    if not isinstance(plane.shape, PlaneShape):
        raise PhysicsValidationError(
            "convex-plane TOI second body must be plane"
        )
    if plane.angular_velocity.length_squared() > 1.0e-24:
        raise PhysicsValidationError(
            "rotating infinite plane CCD is unsupported"
        )


def _plane_support_at_time(
    convex: RigidBody,
    plane: RigidBody,
    time: float,
) -> tuple[float, Vec3, Vec3, Vec3]:
    convex_transform = _predicted_transform(convex, time)
    plane_transform = _predicted_transform(plane, time)
    plane_shape = plane.shape
    assert isinstance(plane_shape, PlaneShape)

    plane_normal, plane_offset = plane_shape.world_equation(
        plane_transform
    )
    point_convex = convex.shape.support(
        -plane_normal,
        convex_transform,
    )
    signed_distance = plane_normal.dot(point_convex) - plane_offset
    point_plane = point_convex - plane_normal * signed_distance

    # Result normal is finite-convex A -> infinite-plane B.
    normal = -plane_normal
    return signed_distance, normal, point_convex, point_plane


def _refine_convex_plane_toi(
    convex: RigidBody,
    plane: RigidBody,
    low: float,
    high: float,
    *,
    distance_tolerance: float,
    time_tolerance: float,
) -> tuple[float, tuple[float, Vec3, Vec3, Vec3]]:
    result = _plane_support_at_time(convex, plane, high)
    for _ in range(64):
        if high - low <= time_tolerance:
            break
        middle = (low + high) * 0.5
        candidate = _plane_support_at_time(
            convex,
            plane,
            middle,
        )
        if candidate[0] <= distance_tolerance:
            high = middle
            result = candidate
        else:
            low = middle
    return high, result


def convex_plane_time_of_impact(
    convex: RigidBody,
    plane: RigidBody,
    dt: float,
    *,
    max_iterations: int = 32,
    distance_tolerance: float = 1.0e-6,
    time_tolerance: float = 1.0e-9,
) -> ConvexTOIResult | None:
    """Conservative TOI for a finite convex body against an infinite plane.

    The plane may translate but must not rotate.  The finite convex body may
    translate and rotate.  The support point in -plane-normal gives exact
    signed separation at each sampled transform; angular motion is bounded by
    the finite shape sweep radius.
    """

    _validate_convex_plane_pair(convex, plane)
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise PhysicsValidationError(
            "convex-plane TOI dt must be numeric"
        )
    dt = float(dt)
    if not math.isfinite(dt) or dt <= 0.0:
        raise PhysicsValidationError(
            "convex-plane TOI dt must be positive"
        )
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or not 1 <= max_iterations <= MAX_CONVEX_TOI_ITERATIONS
    ):
        raise PhysicsValidationError(
            "convex-plane TOI max_iterations outside supported range"
        )
    for name, value in (
        ("distance_tolerance", distance_tolerance),
        ("time_tolerance", time_tolerance),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise PhysicsValidationError(f"{name} must be positive")
    distance_tolerance = float(distance_tolerance)
    time_tolerance = float(time_tolerance)

    sweep_radius = _shape_sweep_radius(convex)
    angular_bound = convex.angular_velocity.length() * sweep_radius
    relative_linear = convex.linear_velocity - plane.linear_velocity

    time = 0.0
    previous_separated_time = 0.0

    for iteration in range(1, max_iterations + 1):
        (
            distance,
            normal,
            point_convex,
            point_plane,
        ) = _plane_support_at_time(convex, plane, time)

        if distance <= distance_tolerance:
            if time > 0.0:
                time, refined = _refine_convex_plane_toi(
                    convex,
                    plane,
                    previous_separated_time,
                    time,
                    distance_tolerance=distance_tolerance,
                    time_tolerance=time_tolerance,
                )
                (
                    distance,
                    normal,
                    point_convex,
                    point_plane,
                ) = refined
            return ConvexTOIResult(
                body_a=convex.body_id,
                body_b=plane.body_id,
                fraction=min(1.0, max(0.0, time / dt)),
                time=time,
                normal=normal,
                point_a=point_convex,
                point_b=point_plane,
                iterations=iteration,
                initial_overlap=time <= time_tolerance,
            )

        plane_normal = -normal
        closing_bound = max(
            0.0,
            -relative_linear.dot(plane_normal) + angular_bound,
        )
        if closing_bound <= EPSILON:
            return None

        advance = (
            distance - distance_tolerance
        ) / closing_bound
        if advance <= 0.0:
            advance = time_tolerance

        previous_separated_time = time
        next_time = time + max(advance, time_tolerance)
        if next_time > dt + time_tolerance:
            return None
        time = min(dt, next_time)

    raise ConvexQueryError(
        "convex-plane TOI iteration bound exceeded"
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


def _epa_horizon_edges(
    visible: list[_EPAFace],
) -> tuple[tuple[int, int], ...]:
    """Return the unique directed horizon of the visible EPA region.

    The horizon is topological: an edge shared by two visible triangles is
    interior regardless of whether floating-point face construction left both
    triangles with the same directed edge. Counting undirected incidences
    prevents duplicate horizon edges from multiplying identical replacement
    faces and corrupting the EPA frontier.
    """

    counts: dict[tuple[int, int], int] = {}
    oriented: dict[tuple[int, int], tuple[int, int]] = {}
    for face in visible:
        for edge in (
            (face.a, face.b),
            (face.b, face.c),
            (face.c, face.a),
        ):
            key = tuple(sorted(edge))
            counts[key] = counts.get(key, 0) + 1
            oriented.setdefault(key, edge)

    if any(count > 2 for count in counts.values()):
        raise ConvexQueryError("EPA visible horizon is non-manifold")

    return tuple(
        oriented[key]
        for key in sorted(counts)
        if counts[key] == 1
    )


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

        boundary = _epa_horizon_edges(visible)
        if not boundary:
            raise ConvexQueryError("EPA visible horizon is empty")

        visible_set = set(visible)
        faces = [face_row for face_row in faces if face_row not in visible_set]

        for edge in boundary:
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
