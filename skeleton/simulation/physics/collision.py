"""Deterministic broad-phase and analytic narrow-phase collision detection.

The narrow phase emits bounded contact manifolds with stable geometric feature
identity. OBB-vs-OBB uses all 15 separating axes. Face contacts use
reference/incident face clipping and deterministic four-point reduction, while
edge contacts use finite closest-segment geometry. Capsule/cylinder pairings use
the bounded convex support-map kernel without replacing proven analytic paths.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .body import BodyType, RigidBody
from .convex import convex_penetration
from .errors import PhysicsValidationError, UnsupportedCollisionError
from .materials import ContactMaterial, combine_materials
from .math3d import EPSILON, AABB, Vec3
from .shapes import (
    BoxShape,
    CapsuleShape,
    ConvexHullShape,
    CylinderShape,
    PlaneShape,
    ShapeKind,
    SphereShape,
)

_AXIS_EPSILON_SQ = 1.0e-16
_CONTACT_POSITION_EPSILON_SQ = 1.0e-18
MAX_BROAD_PHASE_PAIRS = 1_000_000
MAX_MANIFOLD_POINTS = 4


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
    feature_id: str = "primary"

    def __post_init__(self) -> None:
        if not isinstance(self.position, Vec3):
            raise PhysicsValidationError("contact position must be Vec3")
        if not math.isfinite(self.penetration) or self.penetration < 0.0:
            raise PhysicsValidationError("contact penetration must be finite and non-negative")
        if (
            not isinstance(self.feature_id, str)
            or not self.feature_id
            or len(self.feature_id) > 128
            or any(ord(char) < 32 for char in self.feature_id)
        ):
            raise PhysicsValidationError("invalid contact feature_id")


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
        try:
            points = tuple(self.points)
        except TypeError as exc:
            raise PhysicsValidationError("contact manifold points must be iterable") from exc
        if not points:
            raise PhysicsValidationError("contact manifold requires at least one point")
        if len(points) > MAX_MANIFOLD_POINTS:
            raise PhysicsValidationError("contact manifold point bound exceeded")
        if not all(isinstance(point, ContactPoint) for point in points):
            raise PhysicsValidationError("contact manifold contains invalid point")
        features = tuple(point.feature_id for point in points)
        if len(set(features)) != len(features):
            raise PhysicsValidationError("contact manifold feature ids must be unique")
        normalized = self.normal.normalized()
        object.__setattr__(self, "normal", normalized)
        object.__setattr__(self, "points", points)

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


@dataclass(frozen=True, slots=True)
class _ClipVertex:
    position: Vec3
    feature: str


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


def _feature_hash(*parts: str) -> str:
    material = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:16]


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
        (ContactPoint(point, penetration, "sphere:sphere"),),
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
        (ContactPoint(point, max(0.0, penetration), "plane:sphere"),),
        _contact_material(plane, sphere),
    )


def _box_sphere_feature(
    local_center: Vec3,
    half: Vec3,
    *,
    interior_axis: int | None,
    interior_sign: float | None,
) -> str:
    if interior_axis is not None:
        sign_text = "+" if interior_sign is not None and interior_sign > 0.0 else "-"
        return f"box-sphere:face:{interior_axis}{sign_text}"

    features: list[str] = []
    center = local_center.to_tuple()
    extents = half.to_tuple()
    for axis in range(3):
        if center[axis] > extents[axis] - EPSILON:
            features.append(f"{axis}+")
        elif center[axis] < -extents[axis] + EPSILON:
            features.append(f"{axis}-")
    if not features:
        return "box-sphere:interior"
    return "box-sphere:" + ",".join(features)


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
    interior_axis: int | None = None
    interior_sign: float | None = None

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
        interior_axis = min(range(3), key=lambda i: (face_distances[i], i))
        interior_sign = 1.0 if local_center.to_tuple()[interior_axis] >= 0.0 else -1.0
        normal_local = Vec3.axis(interior_axis) * interior_sign
        penetration = sphere_shape.radius + face_distances[interior_axis]
        values = list(local_center.to_tuple())
        values[interior_axis] = half.to_tuple()[interior_axis] * interior_sign
        contact_local = Vec3(*values)

    normal = box.transform.transform_vector(normal_local).normalized()
    point = box.transform.transform_point(contact_local)
    feature_id = _box_sphere_feature(
        local_center,
        half,
        interior_axis=interior_axis,
        interior_sign=interior_sign,
    )
    return ContactManifold(
        box.body_id,
        sphere.body_id,
        normal,
        (ContactPoint(point, max(0.0, penetration), feature_id),),
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


def _vertex_index(signs: tuple[float, float, float]) -> int:
    index = 0
    for axis, sign in enumerate(signs):
        if sign > 0.0:
            index |= 1 << axis
    return index


def _box_vertices(shape: BoxShape, body: RigidBody) -> tuple[tuple[int, Vec3], ...]:
    half = shape.half_extents.to_tuple()
    vertices: list[tuple[int, Vec3]] = []
    for index in range(8):
        signs = tuple(1.0 if index & (1 << axis) else -1.0 for axis in range(3))
        local = Vec3(
            signs[0] * half[0],
            signs[1] * half[1],
            signs[2] * half[2],
        )
        vertices.append((index, body.transform.transform_point(local)))
    return tuple(vertices)


def _box_face_vertices(
    shape: BoxShape,
    body: RigidBody,
    axis_index: int,
    sign: float,
) -> tuple[_ClipVertex, ...]:
    half = shape.half_extents.to_tuple()
    tangent_axes = tuple(axis for axis in range(3) if axis != axis_index)
    corners = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    result: list[_ClipVertex] = []
    for first, second in corners:
        signs = [0.0, 0.0, 0.0]
        signs[axis_index] = sign
        signs[tangent_axes[0]] = first
        signs[tangent_axes[1]] = second
        local = Vec3(
            signs[0] * half[0],
            signs[1] * half[1],
            signs[2] * half[2],
        )
        index = _vertex_index((signs[0], signs[1], signs[2]))
        result.append(
            _ClipVertex(
                position=body.transform.transform_point(local),
                feature=f"v{index}",
            )
        )
    return tuple(result)


def _clip_polygon(
    polygon: tuple[_ClipVertex, ...],
    *,
    normal: Vec3,
    offset: float,
    plane_id: str,
) -> tuple[_ClipVertex, ...]:
    if not polygon:
        return ()

    result: list[_ClipVertex] = []
    previous = polygon[-1]
    previous_distance = normal.dot(previous.position) - offset
    previous_inside = previous_distance <= EPSILON

    for current in polygon:
        current_distance = normal.dot(current.position) - offset
        current_inside = current_distance <= EPSILON

        if previous_inside != current_inside:
            denominator = previous_distance - current_distance
            if abs(denominator) > EPSILON:
                fraction = previous_distance / denominator
                fraction = min(1.0, max(0.0, fraction))
                if fraction <= EPSILON:
                    intersection = previous
                elif fraction >= 1.0 - EPSILON:
                    intersection = current
                else:
                    position = previous.position + (
                        current.position - previous.position
                    ) * fraction
                    features = tuple(sorted((previous.feature, current.feature)))
                    intersection = _ClipVertex(
                        position=position,
                        feature=(
                            f"clip:{plane_id}:"
                            f"{_feature_hash(plane_id, features[0], features[1])}"
                        ),
                    )
                result.append(intersection)

        if current_inside:
            result.append(current)

        previous = current
        previous_distance = current_distance
        previous_inside = current_inside

    deduplicated: list[_ClipVertex] = []
    for vertex in result:
        duplicate = next(
            (
                existing
                for existing in deduplicated
                if (existing.position - vertex.position).length_squared()
                <= _CONTACT_POSITION_EPSILON_SQ
            ),
            None,
        )
        if duplicate is None:
            deduplicated.append(vertex)
    return tuple(deduplicated)


def _reduce_contact_points(
    points: tuple[ContactPoint, ...],
    *,
    max_points: int = MAX_MANIFOLD_POINTS,
) -> tuple[ContactPoint, ...]:
    if not points:
        return ()

    unique: list[ContactPoint] = []
    for point in sorted(points, key=lambda row: row.feature_id):
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(unique)
                if (existing.position - point.position).length_squared()
                <= _CONTACT_POSITION_EPSILON_SQ
            ),
            None,
        )
        if duplicate_index is None:
            unique.append(point)
        else:
            existing = unique[duplicate_index]
            if (
                point.penetration > existing.penetration + EPSILON
                or (
                    abs(point.penetration - existing.penetration) <= EPSILON
                    and point.feature_id < existing.feature_id
                )
            ):
                unique[duplicate_index] = point

    if len(unique) <= max_points:
        return tuple(sorted(unique, key=lambda row: row.feature_id))

    chosen: list[ContactPoint] = [
        sorted(unique, key=lambda row: (-row.penetration, row.feature_id))[0]
    ]

    remaining = [row for row in unique if row not in chosen]
    second = sorted(
        remaining,
        key=lambda row: (
            -(row.position - chosen[0].position).length_squared(),
            row.feature_id,
        ),
    )[0]
    chosen.append(second)

    remaining = [row for row in unique if row not in chosen]
    baseline = chosen[1].position - chosen[0].position
    third = sorted(
        remaining,
        key=lambda row: (
            -baseline.cross(row.position - chosen[0].position).length_squared(),
            row.feature_id,
        ),
    )[0]
    chosen.append(third)

    while len(chosen) < max_points:
        remaining = [row for row in unique if row not in chosen]
        if not remaining:
            break
        candidate = sorted(
            remaining,
            key=lambda row: (
                -min(
                    (row.position - existing.position).length_squared()
                    for existing in chosen
                ),
                row.feature_id,
            ),
        )[0]
        chosen.append(candidate)

    return tuple(sorted(chosen, key=lambda row: row.feature_id))


def _box_box_face_contacts(
    a: RigidBody,
    b: RigidBody,
    *,
    manifold_normal: Vec3,
    minimum_overlap: float,
    reference_body: str,
    reference_axis_index: int,
) -> tuple[ContactPoint, ...]:
    if reference_body == "a":
        reference = a
        incident = b
        reference_shape = a.shape
        incident_shape = b.shape
        reference_normal = manifold_normal
        reference_label = "a"
        incident_label = "b"
    else:
        reference = b
        incident = a
        reference_shape = b.shape
        incident_shape = a.shape
        reference_normal = -manifold_normal
        reference_label = "b"
        incident_label = "a"

    assert isinstance(reference_shape, BoxShape)
    assert isinstance(incident_shape, BoxShape)

    reference_axes = reference_shape.axes(reference.transform)
    incident_axes = incident_shape.axes(incident.transform)
    reference_axis = reference_axes[reference_axis_index]
    reference_sign = 1.0 if reference_axis.dot(reference_normal) >= 0.0 else -1.0
    reference_extent = reference_shape.half_extents.to_tuple()[reference_axis_index]
    face_center = reference.position + reference_axis * (
        reference_sign * reference_extent
    )

    incident_axis_index = max(
        range(3),
        key=lambda index: (
            abs(incident_axes[index].dot(reference_normal)),
            -index,
        ),
    )
    incident_axis = incident_axes[incident_axis_index]
    incident_sign = -1.0 if incident_axis.dot(reference_normal) > 0.0 else 1.0
    polygon = _box_face_vertices(
        incident_shape,
        incident,
        incident_axis_index,
        incident_sign,
    )

    tangent_indices = tuple(
        index for index in range(3) if index != reference_axis_index
    )
    reference_half = reference_shape.half_extents.to_tuple()

    for tangent_index in tangent_indices:
        tangent = reference_axes[tangent_index]
        extent = reference_half[tangent_index]
        polygon = _clip_polygon(
            polygon,
            normal=tangent,
            offset=tangent.dot(face_center) + extent,
            plane_id=f"{reference_label}{reference_axis_index}:t{tangent_index}+",
        )
        polygon = _clip_polygon(
            polygon,
            normal=-tangent,
            offset=(-tangent).dot(face_center) + extent,
            plane_id=f"{reference_label}{reference_axis_index}:t{tangent_index}-",
        )
        if not polygon:
            break

    points: list[ContactPoint] = []
    reference_feature = (
        f"{reference_label}:face:{reference_axis_index}"
        f"{'+' if reference_sign > 0.0 else '-'}"
    )
    incident_feature = (
        f"{incident_label}:face:{incident_axis_index}"
        f"{'+' if incident_sign > 0.0 else '-'}"
    )

    for vertex in polygon:
        separation = (vertex.position - face_center).dot(reference_normal)
        if separation > EPSILON:
            continue
        penetration = max(0.0, -separation)
        position = vertex.position - reference_normal * (separation * 0.5)
        feature_id = (
            f"box-box:{reference_feature}:{incident_feature}:"
            f"{vertex.feature}"
        )
        if len(feature_id) > 128:
            feature_id = (
                f"box-box:{reference_feature}:{incident_feature}:"
                f"h{_feature_hash(feature_id)}"
            )
        points.append(ContactPoint(position, penetration, feature_id))

    reduced = _reduce_contact_points(tuple(points))
    if reduced:
        return reduced

    support_a = a.shape.support(manifold_normal, a.transform)
    support_b = b.shape.support(-manifold_normal, b.transform)
    fallback = (support_a + support_b) * 0.5
    return (
        ContactPoint(
            fallback,
            minimum_overlap,
            (
                f"box-box:{reference_feature}:{incident_feature}:fallback"
            ),
        ),
    )


@dataclass(frozen=True, slots=True)
class _BoxEdge:
    start: Vec3
    end: Vec3
    feature_id: str


def _support_edge(
    shape: BoxShape,
    body: RigidBody,
    *,
    edge_axis_index: int,
    support_direction: Vec3,
    label: str,
) -> _BoxEdge:
    axes = shape.axes(body.transform)
    extents = shape.half_extents.to_tuple()
    center = body.position
    fixed_signs: list[str] = []

    for axis_index, axis in enumerate(axes):
        if axis_index == edge_axis_index:
            continue
        projection = axis.dot(support_direction)
        sign = 1.0 if projection >= 0.0 else -1.0
        center = center + axis * (extents[axis_index] * sign)
        fixed_signs.append(
            f"{axis_index}{'+' if sign > 0.0 else '-'}"
        )

    direction = axes[edge_axis_index]
    extent = extents[edge_axis_index]
    feature = (
        f"{label}:edge:{edge_axis_index}:"
        + ",".join(fixed_signs)
    )
    return _BoxEdge(
        start=center - direction * extent,
        end=center + direction * extent,
        feature_id=feature,
    )


def _closest_segment_points(
    first_start: Vec3,
    first_end: Vec3,
    second_start: Vec3,
    second_end: Vec3,
) -> tuple[Vec3, Vec3, float, float]:
    """Return closest points and normalized parameters on two finite segments."""

    d1 = first_end - first_start
    d2 = second_end - second_start
    relative = first_start - second_start
    a = d1.dot(d1)
    e = d2.dot(d2)
    f = d2.dot(relative)

    if a <= _AXIS_EPSILON_SQ and e <= _AXIS_EPSILON_SQ:
        return first_start, second_start, 0.0, 0.0

    if a <= _AXIS_EPSILON_SQ:
        s = 0.0
        t = min(1.0, max(0.0, f / e))
    else:
        c = d1.dot(relative)
        if e <= _AXIS_EPSILON_SQ:
            t = 0.0
            s = min(1.0, max(0.0, -c / a))
        else:
            b = d1.dot(d2)
            denominator = a * e - b * b
            if abs(denominator) > _AXIS_EPSILON_SQ:
                s = min(
                    1.0,
                    max(0.0, (b * f - c * e) / denominator),
                )
            else:
                # Nearly parallel segments: choose the first endpoint
                # deterministically, then project onto the other segment.
                s = 0.0

            t = (b * s + f) / e
            if t < 0.0:
                t = 0.0
                s = min(1.0, max(0.0, -c / a))
            elif t > 1.0:
                t = 1.0
                s = min(1.0, max(0.0, (b - c) / a))

    first = first_start + d1 * s
    second = second_start + d2 * t
    return first, second, s, t


def _box_box_edge_contact(
    a: RigidBody,
    b: RigidBody,
    *,
    manifold_normal: Vec3,
    penetration: float,
    axis_a_index: int,
    axis_b_index: int,
) -> ContactPoint:
    shape_a = a.shape
    shape_b = b.shape
    assert isinstance(shape_a, BoxShape)
    assert isinstance(shape_b, BoxShape)

    edge_a = _support_edge(
        shape_a,
        a,
        edge_axis_index=axis_a_index,
        support_direction=manifold_normal,
        label="a",
    )
    edge_b = _support_edge(
        shape_b,
        b,
        edge_axis_index=axis_b_index,
        support_direction=-manifold_normal,
        label="b",
    )
    closest_a, closest_b, _, _ = _closest_segment_points(
        edge_a.start,
        edge_a.end,
        edge_b.start,
        edge_b.end,
    )
    point = (closest_a + closest_b) * 0.5
    feature_id = (
        f"box-box:{edge_a.feature_id}:{edge_b.feature_id}"
    )
    if len(feature_id) > 128:
        feature_id = (
            f"box-box:edge-pair:h{_feature_hash(feature_id)}"
        )
    return ContactPoint(
        point,
        penetration,
        feature_id,
    )


def _box_box(a: RigidBody, b: RigidBody) -> ContactManifold | None:
    shape_a = a.shape
    shape_b = b.shape
    assert isinstance(shape_a, BoxShape)
    assert isinstance(shape_b, BoxShape)

    axes_a = shape_a.axes(a.transform)
    axes_b = shape_b.axes(b.transform)
    candidates: list[tuple[Vec3, str, int, int]] = []
    for index, axis in enumerate(axes_a):
        candidates.append((axis, "face_a", index, -1))
    for index, axis in enumerate(axes_b):
        candidates.append((axis, "face_b", index, -1))
    for index_a, axis_a in enumerate(axes_a):
        for index_b, axis_b in enumerate(axes_b):
            cross = axis_a.cross(axis_b)
            if cross.length_squared() > _AXIS_EPSILON_SQ:
                candidates.append(
                    (cross.normalized(), "edge", index_a, index_b)
                )

    center_delta = b.position - a.position
    minimum_overlap = float("inf")
    minimum_axis: Vec3 | None = None
    minimum_kind = ""
    minimum_index_a = -1
    minimum_index_b = -1

    for raw_axis, kind, index_a, index_b in candidates:
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
            minimum_kind = kind
            minimum_index_a = index_a
            minimum_index_b = index_b

    if minimum_axis is None:
        return None
    if center_delta.dot(minimum_axis) < 0.0:
        minimum_axis = -minimum_axis

    if minimum_kind == "face_a":
        points = _box_box_face_contacts(
            a,
            b,
            manifold_normal=minimum_axis,
            minimum_overlap=minimum_overlap,
            reference_body="a",
            reference_axis_index=minimum_index_a,
        )
    elif minimum_kind == "face_b":
        points = _box_box_face_contacts(
            a,
            b,
            manifold_normal=minimum_axis,
            minimum_overlap=minimum_overlap,
            reference_body="b",
            reference_axis_index=minimum_index_a,
        )
    else:
        points = (
            _box_box_edge_contact(
                a,
                b,
                manifold_normal=minimum_axis,
                penetration=minimum_overlap,
                axis_a_index=minimum_index_a,
                axis_b_index=minimum_index_b,
            ),
        )

    return ContactManifold(
        a.body_id,
        b.body_id,
        minimum_axis,
        points,
        _contact_material(a, b),
    )


def _plane_box(plane: RigidBody, box: RigidBody) -> ContactManifold | None:
    plane_shape = plane.shape
    box_shape = box.shape
    assert isinstance(plane_shape, PlaneShape)
    assert isinstance(box_shape, BoxShape)

    normal, offset = plane_shape.world_equation(plane.transform)
    radius = _projection_radius(box_shape, box, normal)
    signed_center_distance = normal.dot(box.position) - offset
    if radius - signed_center_distance < 0.0:
        return None

    points: list[ContactPoint] = []
    for vertex_index, vertex in _box_vertices(box_shape, box):
        signed_distance = normal.dot(vertex) - offset
        if signed_distance <= EPSILON:
            points.append(
                ContactPoint(
                    vertex,
                    max(0.0, -signed_distance),
                    f"plane-box:v{vertex_index}",
                )
            )

    reduced = _reduce_contact_points(tuple(points))
    if not reduced:
        support = box_shape.support(-normal, box.transform)
        penetration = max(
            0.0,
            radius - signed_center_distance,
        )
        reduced = (
            ContactPoint(
                support,
                penetration,
                "plane-box:support",
            ),
        )

    return ContactManifold(
        plane.body_id,
        box.body_id,
        normal,
        reduced,
        _contact_material(plane, box),
    )


def _plane_support_convex(
    plane: RigidBody,
    convex: RigidBody,
) -> ContactManifold | None:
    plane_shape = plane.shape
    assert isinstance(plane_shape, PlaneShape)
    assert isinstance(
        convex.shape,
        (CapsuleShape, CylinderShape, ConvexHullShape),
    )

    normal, offset = plane_shape.world_equation(plane.transform)
    deepest = convex.shape.support(-normal, convex.transform)
    signed_distance = normal.dot(deepest) - offset
    if signed_distance > EPSILON:
        return None

    penetration = max(0.0, -signed_distance)
    projected = deepest - normal * signed_distance
    point = (deepest + projected) * 0.5
    feature = f"plane-{convex.shape.kind.value}:support"
    return ContactManifold(
        plane.body_id,
        convex.body_id,
        normal,
        (ContactPoint(point, penetration, feature),),
        _contact_material(plane, convex),
    )


def _convex_convex(
    a: RigidBody,
    b: RigidBody,
) -> ContactManifold | None:
    penetration = convex_penetration(
        a,
        b,
        gjk_iterations=64,
        epa_iterations=96,
        tolerance=1.0e-6,
    )
    if penetration is None:
        return None

    normal = penetration.normal
    center_delta = b.position - a.position
    if (
        center_delta.length_squared() > _AXIS_EPSILON_SQ
        and center_delta.dot(normal) < 0.0
    ):
        normal = -normal

    feature = (
        f"convex:{a.shape.kind.value}:{b.shape.kind.value}:primary"
    )
    return ContactManifold(
        a.body_id,
        b.body_id,
        normal,
        (
            ContactPoint(
                penetration.contact_point,
                penetration.depth,
                feature,
            ),
        ),
        _contact_material(a, b),
    )


def detect_collision(a: RigidBody, b: RigidBody) -> ContactManifold | None:
    """Return one deterministic bounded manifold for a supported body pair."""

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

    support_convex = {
        ShapeKind.CAPSULE,
        ShapeKind.CYLINDER,
        ShapeKind.CONVEX_HULL,
    }
    if kind_a is ShapeKind.PLANE and kind_b in support_convex:
        return _plane_support_convex(a, b)
    if kind_b is ShapeKind.PLANE and kind_a in support_convex:
        result = _plane_support_convex(b, a)
        return None if result is None else result.flipped()

    finite_convex = {
        ShapeKind.SPHERE,
        ShapeKind.BOX,
        ShapeKind.CAPSULE,
        ShapeKind.CYLINDER,
        ShapeKind.CONVEX_HULL,
    }
    if (
        kind_a in finite_convex
        and kind_b in finite_convex
        and (kind_a in support_convex or kind_b in support_convex)
    ):
        return _convex_convex(a, b)

    raise UnsupportedCollisionError(
        f"unsupported collision pair: {kind_a.value}/{kind_b.value}"
    )


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
