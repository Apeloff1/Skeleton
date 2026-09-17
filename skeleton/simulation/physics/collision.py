"""Deterministic broad-phase and narrow-phase collision detection.

The initial narrow phase deliberately concentrates on analytic game-workhorse
shapes: sphere, oriented box, and infinite plane.  OBB-vs-OBB uses all 15
separating-axis candidates (three face axes per box plus nine edge cross axes).
"""
from __future__ import annotations

from dataclasses import dataclass

from .body import BodyType, RigidBody
from .errors import PhysicsValidationError, UnsupportedCollisionError
from .materials import ContactMaterial, combine_materials
from .math3d import EPSILON, AABB, Vec3
from .shapes import BoxShape, PlaneShape, ShapeKind, SphereShape

_AXIS_EPSILON_SQ = 1.0e-16
MAX_BROAD_PHASE_PAIRS = 1_000_000


@dataclass(frozen=True, slots=True)
class BroadPhasePair:
    body_a: str
    body_b: str

    def __post_init__(self) -> None:
        if self.body_a >= self.body_b:
            raise PhysicsValidationError("broad-phase pair ids must be strictly ordered")


@dataclass(frozen=True, slots=True)
class ContactPoint:
    position: Vec3
    penetration: float

    def __post_init__(self) -> None:
        if self.penetration < 0.0:
            raise PhysicsValidationError("contact penetration must be non-negative")


@dataclass(frozen=True, slots=True)
class ContactManifold:
    """Contact normal points from body A toward body B."""

    body_a: str
    body_b: str
    normal: Vec3
    points: tuple[ContactPoint, ...]
    material: ContactMaterial

    def __post_init__(self) -> None:
        if self.body_a == self.body_b:
            raise PhysicsValidationError("contact manifold requires distinct bodies")
        if not self.points:
            raise PhysicsValidationError("contact manifold requires at least one point")
        normalized = self.normal.normalized()
        object.__setattr__(self, "normal", normalized)
        object.__setattr__(self, "points", tuple(self.points))

    @property
    def penetration(self) -> float:
        return max((point.penetration for point in self.points), default=0.0)

    def flipped(self) -> "ContactManifold":
        return ContactManifold(
            body_a=self.body_b,
            body_b=self.body_a,
            normal=-self.normal,
            points=self.points,
            material=self.material,
        )


def _ordered_pair(left: RigidBody, right: RigidBody) -> tuple[RigidBody, RigidBody]:
    return (left, right) if left.body_id < right.body_id else (right, left)


def _needs_physical_pair(left: RigidBody, right: RigidBody) -> bool:
    return left.body_type is BodyType.DYNAMIC or right.body_type is BodyType.DYNAMIC


class SweepAndPruneBroadPhase:
    """Stable one-axis sweep with full-AABB rejection."""

    def __init__(self, *, max_pairs: int = 250_000) -> None:
        if (
            isinstance(max_pairs, bool)
            or not isinstance(max_pairs, int)
            or not 1 <= max_pairs <= MAX_BROAD_PHASE_PAIRS
        ):
            raise PhysicsValidationError("max_pairs outside supported range")
        self.max_pairs = max_pairs

    def _add_pair(self, pairs: set[BroadPhasePair], pair: BroadPhasePair) -> None:
        if pair in pairs:
            return
        if len(pairs) >= self.max_pairs:
            raise PhysicsValidationError("broad-phase pair bound exceeded")
        pairs.add(pair)

    def compute_pairs(self, bodies: tuple[RigidBody, ...]) -> tuple[BroadPhasePair, ...]:
        finite: list[tuple[float, str, RigidBody, AABB]] = []
        planes: list[RigidBody] = []

        for body in sorted(bodies, key=lambda row: row.body_id):
            bounds = body.shape.aabb(body.transform)
            if bounds is None:
                planes.append(body)
            else:
                finite.append((bounds.minimum.x, body.body_id, body, bounds))

        finite.sort(key=lambda row: (row[0], row[1]))
        active: list[tuple[float, str, RigidBody, AABB]] = []
        pairs: set[BroadPhasePair] = set()

        for _, _, body, bounds in finite:
            active = [row for row in active if row[0] + EPSILON >= bounds.minimum.x]
            for _, _, other, other_bounds in active:
                if not _needs_physical_pair(body, other):
                    continue
                if bounds.overlaps(other_bounds):
                    left, right = _ordered_pair(body, other)
                    self._add_pair(pairs, BroadPhasePair(left.body_id, right.body_id))
            active.append((bounds.maximum.x, body.body_id, body, bounds))
            active.sort(key=lambda row: (row[0], row[1]))

        for plane in sorted(planes, key=lambda row: row.body_id):
            for body in sorted(bodies, key=lambda row: row.body_id):
                if body.body_id == plane.body_id or isinstance(body.shape, PlaneShape):
                    continue
                if not _needs_physical_pair(plane, body):
                    continue
                left, right = _ordered_pair(plane, body)
                self._add_pair(pairs, BroadPhasePair(left.body_id, right.body_id))

        return tuple(sorted(pairs, key=lambda row: (row.body_a, row.body_b)))


def _contact_material(a: RigidBody, b: RigidBody) -> ContactMaterial:
    return combine_materials(a.material, b.material)


def _sphere_sphere(a: RigidBody, b: RigidBody) -> ContactManifold | None:
    shape_a = a.shape
    shape_b = b.shape
    assert isinstance(shape_a, SphereShape)
    assert isinstance(shape_b, SphereShape)

    delta = b.position - a.position
    radius_sum = shape_a.radius + shape_b.radius
    distance_sq = delta.length_squared()
    if distance_sq > radius_sum * radius_sum:
        return None

    if distance_sq <= _AXIS_EPSILON_SQ:
        normal = Vec3.axis(0)
        distance = 0.0
    else:
        distance = distance_sq**0.5
        normal = delta / distance

    penetration = max(0.0, radius_sum - distance)
    surface_a = a.position + normal * shape_a.radius
    surface_b = b.position - normal * shape_b.radius
    point = (surface_a + surface_b) * 0.5
    return ContactManifold(
        a.body_id,
        b.body_id,
        normal,
        (ContactPoint(point, penetration),),
        _contact_material(a, b),
    )


def _plane_sphere(plane: RigidBody, sphere: RigidBody) -> ContactManifold | None:
    plane_shape = plane.shape
    sphere_shape = sphere.shape
    assert isinstance(plane_shape, PlaneShape)
    assert isinstance(sphere_shape, SphereShape)

    normal, offset = plane_shape.world_equation(plane.transform)
    signed_distance = normal.dot(sphere.position) - offset
    penetration = sphere_shape.radius - signed_distance
    if penetration < 0.0:
        return None
    point = sphere.position - normal * sphere_shape.radius
    return ContactManifold(
        plane.body_id,
        sphere.body_id,
        normal,
        (ContactPoint(point, max(0.0, penetration)),),
        _contact_material(plane, sphere),
    )


def _box_sphere(box: RigidBody, sphere: RigidBody) -> ContactManifold | None:
    box_shape = box.shape
    sphere_shape = sphere.shape
    assert isinstance(box_shape, BoxShape)
    assert isinstance(sphere_shape, SphereShape)

    local_center = box.transform.inverse_transform_point(sphere.position)
    half = box_shape.half_extents
    closest_local = local_center.clamp(-half, half)
    delta_local = local_center - closest_local
    distance_sq = delta_local.length_squared()

    if distance_sq > sphere_shape.radius * sphere_shape.radius:
        return None

    if distance_sq > _AXIS_EPSILON_SQ:
        distance = distance_sq**0.5
        normal_local = delta_local / distance
        penetration = sphere_shape.radius - distance
        contact_local = closest_local
    else:
        face_distances = (
            half.x - abs(local_center.x),
            half.y - abs(local_center.y),
            half.z - abs(local_center.z),
        )
        axis_index = min(range(3), key=lambda i: (face_distances[i], i))
        sign = 1.0 if local_center.to_tuple()[axis_index] >= 0.0 else -1.0
        normal_local = Vec3.axis(axis_index) * sign
        penetration = sphere_shape.radius + face_distances[axis_index]
        values = list(local_center.to_tuple())
        values[axis_index] = half.to_tuple()[axis_index] * sign
        contact_local = Vec3(*values)

    normal = box.transform.transform_vector(normal_local).normalized()
    point = box.transform.transform_point(contact_local)
    return ContactManifold(
        box.body_id,
        sphere.body_id,
        normal,
        (ContactPoint(point, max(0.0, penetration)),),
        _contact_material(box, sphere),
    )


def _projection_radius(box: BoxShape, body: RigidBody, axis: Vec3) -> float:
    axes = box.axes(body.transform)
    half = box.half_extents
    return (
        half.x * abs(axis.dot(axes[0]))
        + half.y * abs(axis.dot(axes[1]))
        + half.z * abs(axis.dot(axes[2]))
    )


def _box_box(a: RigidBody, b: RigidBody) -> ContactManifold | None:
    shape_a = a.shape
    shape_b = b.shape
    assert isinstance(shape_a, BoxShape)
    assert isinstance(shape_b, BoxShape)

    axes_a = shape_a.axes(a.transform)
    axes_b = shape_b.axes(b.transform)
    candidates: list[Vec3] = [*axes_a, *axes_b]
    for axis_a in axes_a:
        for axis_b in axes_b:
            cross = axis_a.cross(axis_b)
            if cross.length_squared() > _AXIS_EPSILON_SQ:
                candidates.append(cross.normalized())

    center_delta = b.position - a.position
    minimum_overlap = float("inf")
    minimum_axis: Vec3 | None = None

    for raw_axis in candidates:
        axis = raw_axis.normalized()
        radius_a = _projection_radius(shape_a, a, axis)
        radius_b = _projection_radius(shape_b, b, axis)
        separation = abs(center_delta.dot(axis))
        overlap = radius_a + radius_b - separation
        if overlap < -EPSILON:
            return None
        overlap = max(0.0, overlap)
        if overlap < minimum_overlap:
            minimum_overlap = overlap
            minimum_axis = axis

    if minimum_axis is None:
        return None
    if center_delta.dot(minimum_axis) < 0.0:
        minimum_axis = -minimum_axis

    support_a = shape_a.support(minimum_axis, a.transform)
    support_b = shape_b.support(-minimum_axis, b.transform)
    point = (support_a + support_b) * 0.5
    return ContactManifold(
        a.body_id,
        b.body_id,
        minimum_axis,
        (ContactPoint(point, minimum_overlap),),
        _contact_material(a, b),
    )


def _plane_box(plane: RigidBody, box: RigidBody) -> ContactManifold | None:
    plane_shape = plane.shape
    box_shape = box.shape
    assert isinstance(plane_shape, PlaneShape)
    assert isinstance(box_shape, BoxShape)

    normal, offset = plane_shape.world_equation(plane.transform)
    radius = _projection_radius(box_shape, box, normal)
    signed_distance = normal.dot(box.position) - offset
    penetration = radius - signed_distance
    if penetration < 0.0:
        return None
    point = box_shape.support(-normal, box.transform)
    return ContactManifold(
        plane.body_id,
        box.body_id,
        normal,
        (ContactPoint(point, max(0.0, penetration)),),
        _contact_material(plane, box),
    )


def detect_collision(a: RigidBody, b: RigidBody) -> ContactManifold | None:
    """Return one deterministic manifold for a supported body pair."""

    kind_a = a.shape.kind
    kind_b = b.shape.kind

    if kind_a is ShapeKind.SPHERE and kind_b is ShapeKind.SPHERE:
        return _sphere_sphere(a, b)
    if kind_a is ShapeKind.PLANE and kind_b is ShapeKind.SPHERE:
        return _plane_sphere(a, b)
    if kind_a is ShapeKind.SPHERE and kind_b is ShapeKind.PLANE:
        result = _plane_sphere(b, a)
        return None if result is None else result.flipped()
    if kind_a is ShapeKind.BOX and kind_b is ShapeKind.SPHERE:
        return _box_sphere(a, b)
    if kind_a is ShapeKind.SPHERE and kind_b is ShapeKind.BOX:
        result = _box_sphere(b, a)
        return None if result is None else result.flipped()
    if kind_a is ShapeKind.BOX and kind_b is ShapeKind.BOX:
        return _box_box(a, b)
    if kind_a is ShapeKind.PLANE and kind_b is ShapeKind.BOX:
        return _plane_box(a, b)
    if kind_a is ShapeKind.BOX and kind_b is ShapeKind.PLANE:
        result = _plane_box(b, a)
        return None if result is None else result.flipped()
    if kind_a is ShapeKind.PLANE and kind_b is ShapeKind.PLANE:
        return None

    raise UnsupportedCollisionError(f"unsupported collision pair: {kind_a.value}/{kind_b.value}")


def generate_manifolds(
    bodies: dict[str, RigidBody],
    pairs: tuple[BroadPhasePair, ...],
) -> tuple[ContactManifold, ...]:
    manifolds: list[ContactManifold] = []
    for pair in pairs:
        manifold = detect_collision(bodies[pair.body_a], bodies[pair.body_b])
        if manifold is not None and manifold.points:
            manifolds.append(manifold)
    return tuple(manifolds)
