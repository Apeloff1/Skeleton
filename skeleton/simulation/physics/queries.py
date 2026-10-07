"""Deterministic scene queries for gameplay, AI, editor, and CCD building blocks."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import RigidBody
from .errors import PhysicsValidationError
from .math3d import EPSILON, Vec3
from .shapes import (
    BoxShape,
    CapsuleShape,
    CylinderShape,
    PlaneShape,
    SphereShape,
)


def _distance(value: float, *, name: str, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    valid = value >= 0.0 if allow_zero else value > 0.0
    if not math.isfinite(value) or not valid:
        raise PhysicsValidationError(f"invalid {name}")
    return value


@dataclass(frozen=True, slots=True)
class Ray:
    origin: Vec3
    direction: Vec3
    max_distance: float = 1_000_000.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "direction", self.direction.normalized())
        object.__setattr__(
            self,
            "max_distance",
            _distance(self.max_distance, name="max_distance", allow_zero=True),
        )

    def point_at(self, distance: float) -> Vec3:
        distance = _distance(distance, name="distance", allow_zero=True)
        return self.origin + self.direction * distance


@dataclass(frozen=True, slots=True)
class RayHit:
    body_id: str
    distance: float
    point: Vec3
    normal: Vec3

    def __post_init__(self) -> None:
        if self.distance < 0.0 or not math.isfinite(self.distance):
            raise PhysicsValidationError("ray hit distance must be finite and non-negative")
        object.__setattr__(self, "normal", self.normal.normalized())


def _sphere_intersection(
    ray: Ray,
    center: Vec3,
    radius: float,
    body_id: str,
) -> RayHit | None:
    relative = ray.origin - center
    projected = relative.dot(ray.direction)
    c = relative.length_squared() - radius * radius
    if c > 0.0 and projected > 0.0:
        return None

    discriminant = projected * projected - c
    if discriminant < 0.0:
        return None

    distance = -projected - math.sqrt(max(0.0, discriminant))
    if distance < 0.0:
        distance = 0.0
    if distance > ray.max_distance:
        return None

    point = ray.point_at(distance)
    normal = (point - center).normalized_or_zero()
    if normal.length_squared() <= EPSILON * EPSILON:
        normal = -ray.direction
    return RayHit(body_id, distance, point, normal)


def _plane_intersection(ray: Ray, body: RigidBody, shape: PlaneShape) -> RayHit | None:
    normal, offset = shape.world_equation(body.transform)
    denominator = normal.dot(ray.direction)
    if abs(denominator) <= EPSILON:
        return None
    distance = (offset - normal.dot(ray.origin)) / denominator
    if distance < 0.0 or distance > ray.max_distance:
        return None
    hit_normal = normal if denominator < 0.0 else -normal
    return RayHit(body.body_id, distance, ray.point_at(distance), hit_normal)


def _box_intersection(
    ray: Ray,
    body: RigidBody,
    shape: BoxShape,
    *,
    expansion: float = 0.0,
) -> RayHit | None:
    local_origin = body.transform.inverse_transform_point(ray.origin)
    local_direction = body.transform.inverse_transform_vector(ray.direction)
    half = shape.half_extents + Vec3.one() * expansion

    t_min = 0.0
    t_max = ray.max_distance
    hit_axis = -1
    hit_sign = 0.0

    origins = local_origin.to_tuple()
    directions = local_direction.to_tuple()
    extents = half.to_tuple()

    for axis in range(3):
        origin = origins[axis]
        direction = directions[axis]
        extent = extents[axis]

        if abs(direction) <= EPSILON:
            if origin < -extent or origin > extent:
                return None
            continue

        inverse_direction = 1.0 / direction
        t1 = (-extent - origin) * inverse_direction
        t2 = (extent - origin) * inverse_direction
        near_sign = -1.0
        if t1 > t2:
            t1, t2 = t2, t1
            near_sign = 1.0

        if t1 > t_min:
            t_min = t1
            hit_axis = axis
            hit_sign = near_sign
        t_max = min(t_max, t2)
        if t_min > t_max:
            return None

    distance = max(0.0, t_min)
    if distance > ray.max_distance:
        return None

    if hit_axis < 0:
        # Origin is inside the box: make the query normal oppose travel.
        components = [abs(value) for value in directions]
        hit_axis = max(range(3), key=lambda index: (components[index], -index))
        hit_sign = -1.0 if directions[hit_axis] >= 0.0 else 1.0

    local_normal = Vec3.axis(hit_axis) * hit_sign
    normal = body.transform.transform_vector(local_normal).normalized()
    return RayHit(body.body_id, distance, ray.point_at(distance), normal)


def _local_sphere_roots(
    origin: Vec3,
    direction: Vec3,
    center: Vec3,
    radius: float,
) -> tuple[float, ...]:
    relative = origin - center
    projected = relative.dot(direction)
    c = relative.length_squared() - radius * radius
    discriminant = projected * projected - c
    if discriminant < 0.0:
        return ()
    root = math.sqrt(max(0.0, discriminant))
    return tuple(sorted((-projected - root, -projected + root)))


def _capsule_intersection(
    ray: Ray,
    body: RigidBody,
    shape: CapsuleShape,
) -> RayHit | None:
    origin = body.transform.inverse_transform_point(ray.origin)
    direction = body.transform.inverse_transform_vector(ray.direction).normalized()
    radius = shape.radius
    half_height = shape.half_height

    closest_y = min(half_height, max(-half_height, origin.y))
    inside_delta = origin - Vec3(0.0, closest_y, 0.0)
    if inside_delta.length_squared() <= radius * radius:
        normal = body.transform.transform_vector(-direction).normalized()
        return RayHit(body.body_id, 0.0, ray.origin, normal)

    candidates: list[tuple[float, int, Vec3]] = []

    radial_a = direction.x * direction.x + direction.z * direction.z
    if radial_a > EPSILON * EPSILON:
        radial_b = 2.0 * (
            origin.x * direction.x + origin.z * direction.z
        )
        radial_c = origin.x * origin.x + origin.z * origin.z - radius * radius
        discriminant = radial_b * radial_b - 4.0 * radial_a * radial_c
        if discriminant >= 0.0:
            root = math.sqrt(max(0.0, discriminant))
            inverse = 0.5 / radial_a
            for distance in sorted(
                (
                    (-radial_b - root) * inverse,
                    (-radial_b + root) * inverse,
                )
            ):
                if distance < 0.0 or distance > ray.max_distance:
                    continue
                point = origin + direction * distance
                if -half_height - EPSILON <= point.y <= half_height + EPSILON:
                    local_normal = Vec3(point.x, 0.0, point.z).normalized_or_zero()
                    if local_normal.length_squared() > EPSILON * EPSILON:
                        candidates.append((distance, 0, local_normal))

    for cap_sign, priority in ((1.0, 1), (-1.0, 2)):
        center = Vec3(0.0, cap_sign * half_height, 0.0)
        for distance in _local_sphere_roots(
            origin,
            direction,
            center,
            radius,
        ):
            if distance < 0.0 or distance > ray.max_distance:
                continue
            point = origin + direction * distance
            if (
                cap_sign > 0.0
                and point.y < half_height - EPSILON
            ) or (
                cap_sign < 0.0
                and point.y > -half_height + EPSILON
            ):
                continue
            local_normal = (point - center).normalized_or_zero()
            if local_normal.length_squared() > EPSILON * EPSILON:
                candidates.append((distance, priority, local_normal))
                break

    if not candidates:
        return None
    distance, _, local_normal = min(
        candidates,
        key=lambda row: (row[0], row[1]),
    )
    normal = body.transform.transform_vector(local_normal).normalized()
    return RayHit(
        body.body_id,
        distance,
        ray.point_at(distance),
        normal,
    )


def _cylinder_intersection(
    ray: Ray,
    body: RigidBody,
    shape: CylinderShape,
) -> RayHit | None:
    origin = body.transform.inverse_transform_point(ray.origin)
    direction = body.transform.inverse_transform_vector(ray.direction).normalized()
    radius = shape.radius
    half_height = shape.half_height
    radial_sq = origin.x * origin.x + origin.z * origin.z

    if radial_sq <= radius * radius and abs(origin.y) <= half_height:
        normal = body.transform.transform_vector(-direction).normalized()
        return RayHit(body.body_id, 0.0, ray.origin, normal)

    candidates: list[tuple[float, int, Vec3]] = []
    radial_a = direction.x * direction.x + direction.z * direction.z
    if radial_a > EPSILON * EPSILON:
        radial_b = 2.0 * (
            origin.x * direction.x + origin.z * direction.z
        )
        radial_c = radial_sq - radius * radius
        discriminant = radial_b * radial_b - 4.0 * radial_a * radial_c
        if discriminant >= 0.0:
            root = math.sqrt(max(0.0, discriminant))
            inverse = 0.5 / radial_a
            for distance in sorted(
                (
                    (-radial_b - root) * inverse,
                    (-radial_b + root) * inverse,
                )
            ):
                if distance < 0.0 or distance > ray.max_distance:
                    continue
                point = origin + direction * distance
                if -half_height - EPSILON <= point.y <= half_height + EPSILON:
                    normal = Vec3(point.x, 0.0, point.z).normalized_or_zero()
                    if normal.length_squared() > EPSILON * EPSILON:
                        candidates.append((distance, 0, normal))

    if abs(direction.y) > EPSILON:
        for cap_sign, priority in ((1.0, 1), (-1.0, 2)):
            distance = (
                cap_sign * half_height - origin.y
            ) / direction.y
            if distance < 0.0 or distance > ray.max_distance:
                continue
            point = origin + direction * distance
            if point.x * point.x + point.z * point.z <= radius * radius + EPSILON:
                candidates.append(
                    (
                        distance,
                        priority,
                        Vec3(0.0, cap_sign, 0.0),
                    )
                )

    if not candidates:
        return None
    distance, _, local_normal = min(
        candidates,
        key=lambda row: (row[0], row[1]),
    )
    normal = body.transform.transform_vector(local_normal).normalized()
    return RayHit(
        body.body_id,
        distance,
        ray.point_at(distance),
        normal,
    )


def raycast_body(ray: Ray, body: RigidBody) -> RayHit | None:
    shape = body.shape
    if isinstance(shape, SphereShape):
        return _sphere_intersection(ray, body.position, shape.radius, body.body_id)
    if isinstance(shape, PlaneShape):
        return _plane_intersection(ray, body, shape)
    if isinstance(shape, BoxShape):
        return _box_intersection(ray, body, shape)
    if isinstance(shape, CapsuleShape):
        return _capsule_intersection(ray, body, shape)
    if isinstance(shape, CylinderShape):
        return _cylinder_intersection(ray, body, shape)
    raise PhysicsValidationError("unsupported raycast shape")


def _sphere_cast_box(
    ray: Ray,
    radius: float,
    body: RigidBody,
    shape: BoxShape,
) -> RayHit | None:
    """First center-of-sphere hit against an OBB radius offset.

    The distance from a point on a line to a convex box is a convex function of
    line parameter. We first bound the possible interval with an expanded OBB,
    locate the minimum separation deterministically, then bisect the first root.
    This avoids the square-corner false positives of a plain expanded-box slab.
    """

    local_origin = body.transform.inverse_transform_point(ray.origin)
    local_direction = body.transform.inverse_transform_vector(ray.direction).normalized()
    half = shape.half_extents
    expanded = half + Vec3.one() * radius

    t_min = 0.0
    t_max = ray.max_distance
    origins = local_origin.to_tuple()
    directions = local_direction.to_tuple()
    extents = expanded.to_tuple()

    for axis in range(3):
        origin = origins[axis]
        direction = directions[axis]
        extent = extents[axis]
        if abs(direction) <= EPSILON:
            if origin < -extent or origin > extent:
                return None
            continue
        inverse = 1.0 / direction
        near = (-extent - origin) * inverse
        far = (extent - origin) * inverse
        if near > far:
            near, far = far, near
        t_min = max(t_min, near)
        t_max = min(t_max, far)
        if t_min > t_max:
            return None

    tolerance = max(1.0e-9, radius * 1.0e-8)

    def separation_at(distance: float) -> float:
        center = local_origin + local_direction * distance
        closest = center.clamp(-half, half)
        return (center - closest).length()

    def make_hit(distance: float) -> RayHit:
        center = local_origin + local_direction * distance
        closest = center.clamp(-half, half)
        delta = center - closest
        separation = delta.length()
        if separation > EPSILON:
            local_normal = delta / separation
        else:
            face_distances = (
                half.x - abs(center.x),
                half.y - abs(center.y),
                half.z - abs(center.z),
            )
            axis_index = min(range(3), key=lambda index: (face_distances[index], index))
            sign = 1.0 if center.to_tuple()[axis_index] >= 0.0 else -1.0
            local_normal = Vec3.axis(axis_index) * sign
        normal = body.transform.transform_vector(local_normal).normalized()
        return RayHit(body.body_id, distance, ray.point_at(distance), normal)

    if separation_at(t_min) <= radius + tolerance:
        return make_hit(t_min)

    if t_max <= t_min:
        return None

    low = t_min
    high = t_max
    for _ in range(64):
        third = (high - low) / 3.0
        left = low + third
        right = high - third
        if separation_at(left) <= separation_at(right):
            high = right
        else:
            low = left
    minimum_t = (low + high) * 0.5

    if separation_at(minimum_t) > radius + tolerance:
        return None

    low = t_min
    high = minimum_t
    for _ in range(64):
        middle = (low + high) * 0.5
        if separation_at(middle) <= radius + tolerance:
            high = middle
        else:
            low = middle
    return make_hit(high)

def _sphere_cast_cylinder(
    ray: Ray,
    radius: float,
    body: RigidBody,
    shape: CylinderShape,
) -> RayHit | None:
    """First sphere-center hit against the exact finite-cylinder distance field."""

    origin = body.transform.inverse_transform_point(ray.origin)
    direction = body.transform.inverse_transform_vector(ray.direction).normalized()
    target_radius = shape.radius
    half_height = shape.half_height
    expanded = Vec3(
        target_radius + radius,
        half_height + radius,
        target_radius + radius,
    )

    t_min = 0.0
    t_max = ray.max_distance
    origins = origin.to_tuple()
    directions = direction.to_tuple()
    extents = expanded.to_tuple()
    for axis in range(3):
        axis_origin = origins[axis]
        axis_direction = directions[axis]
        extent = extents[axis]
        if abs(axis_direction) <= EPSILON:
            if axis_origin < -extent or axis_origin > extent:
                return None
            continue
        inverse = 1.0 / axis_direction
        near = (-extent - axis_origin) * inverse
        far = (extent - axis_origin) * inverse
        if near > far:
            near, far = far, near
        t_min = max(t_min, near)
        t_max = min(t_max, far)
        if t_min > t_max:
            return None

    tolerance = max(1.0e-9, radius * 1.0e-8)

    def closest_point(center: Vec3) -> Vec3:
        radial = math.hypot(center.x, center.z)
        if radial > target_radius and radial > EPSILON:
            scale = target_radius / radial
            closest_x = center.x * scale
            closest_z = center.z * scale
        else:
            closest_x = center.x
            closest_z = center.z
        closest_y = min(half_height, max(-half_height, center.y))
        return Vec3(closest_x, closest_y, closest_z)

    def separation_at(distance: float) -> float:
        center = origin + direction * distance
        return (center - closest_point(center)).length()

    def make_hit(distance: float) -> RayHit:
        center = origin + direction * distance
        delta = center - closest_point(center)
        separation = delta.length()
        local_normal = (
            delta / separation
            if separation > EPSILON
            else -direction
        )
        normal = body.transform.transform_vector(local_normal).normalized()
        return RayHit(
            body.body_id,
            distance,
            ray.point_at(distance),
            normal,
        )

    if separation_at(t_min) <= radius + tolerance:
        return make_hit(t_min)
    if t_max <= t_min:
        return None

    low = t_min
    high = t_max
    for _ in range(64):
        third = (high - low) / 3.0
        left = low + third
        right = high - third
        if separation_at(left) <= separation_at(right):
            high = right
        else:
            low = left
    minimum_t = (low + high) * 0.5
    if separation_at(minimum_t) > radius + tolerance:
        return None

    low = t_min
    high = minimum_t
    for _ in range(64):
        middle = (low + high) * 0.5
        if separation_at(middle) <= radius + tolerance:
            high = middle
        else:
            low = middle
    return make_hit(high)


def sphere_cast_body(
    ray: Ray,
    radius: float,
    body: RigidBody,
) -> RayHit | None:
    """Cast a sphere center along a ray using Minkowski-expanded primitives.

    The returned point is the sphere center at first contact.  This is directly
    useful as a conservative TOI primitive for character motion and CCD.
    """

    radius = _distance(radius, name="radius")
    shape = body.shape
    if isinstance(shape, SphereShape):
        return _sphere_intersection(
            ray,
            body.position,
            shape.radius + radius,
            body.body_id,
        )
    if isinstance(shape, BoxShape):
        return _sphere_cast_box(ray, radius, body, shape)
    if isinstance(shape, CapsuleShape):
        expanded = CapsuleShape(
            shape.radius + radius,
            shape.half_height,
        )
        return _capsule_intersection(ray, body, expanded)
    if isinstance(shape, CylinderShape):
        return _sphere_cast_cylinder(ray, radius, body, shape)
    if isinstance(shape, PlaneShape):
        normal, offset = shape.world_equation(body.transform)
        signed_origin = normal.dot(ray.origin) - offset
        denominator = normal.dot(ray.direction)

        if signed_origin <= radius:
            return RayHit(body.body_id, 0.0, ray.origin, normal)
        if denominator >= -EPSILON:
            return None

        distance = (radius - signed_origin) / denominator
        if distance < 0.0 or distance > ray.max_distance:
            return None
        return RayHit(body.body_id, distance, ray.point_at(distance), normal)

    raise PhysicsValidationError("unsupported sphere-cast shape")


def sort_hits(hits: list[RayHit]) -> tuple[RayHit, ...]:
    return tuple(sorted(hits, key=lambda row: (row.distance, row.body_id)))
