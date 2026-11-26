"""Sphere-sphere and sphere-box contact manifolds.

Sphere-sphere continuous detection calls ``sweep_spheres`` and does not keep a
second quadratic. Sphere-box faces call ``sweep_sphere_plane`` and keep the hit
only when the contact lies on the finite rectangle. Edges and corners are
analytic so a fast sphere cannot slip through the rounded Minkowski boundary
between ticks. The discrete slab predicate is the one owned by
``skeleton.frontier_runtime.contacts``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from skeleton.frontier_contact.bodies import BoxBody, SphereBody
from skeleton.frontier_contact.errors import ContactRejected
from skeleton.frontier_runtime.contacts import discrete_sphere_tunnels
from skeleton.jeeves.game_frontier_advanced_physics import (
    CollisionContact,
    RigidBody,
    Vec3,
    sweep_sphere_plane,
    sweep_spheres,
    vecnorm,
)
from skeleton.jeeves.game_frontier_production import FrontierProductionError

_FACE_TOLERANCE_M = 1e-5
_TIME_TOLERANCE_S = 1e-9


@dataclass(frozen=True)
class ManifoldPoint:
    point: tuple[float, float, float]
    normal_a_to_b: tuple[float, float, float]
    penetration_m: float
    feature: str


@dataclass(frozen=True)
class ContactManifold:
    """One or more contact points for a single pair. Spheres produce one."""

    time_of_impact_s: float
    points: tuple[ManifoldPoint, ...]
    source: str
    body_a: str
    body_b: str


def discrete_slab_miss(
    start: tuple[float, float, float],
    velocity: tuple[float, float, float],
    radius_m: float,
    dt: float,
    wall_point: tuple[float, float, float],
    wall_normal: tuple[float, float, float],
    half_thickness_m: float,
) -> bool:
    """True when end samples miss a slab the segment still crosses.

    Delegates to the fixed-step runtime so this package does not keep a second
    copy of the discrete tunnel predicate.
    """
    return discrete_sphere_tunnels(
        start,
        velocity,
        radius_m,
        dt,
        wall_point,
        wall_normal,
        half_thickness_m,
    )


def _vec(value: tuple[float, float, float]) -> Vec3:
    return Vec3(value[0], value[1], value[2])


def _tup(value: Vec3) -> tuple[float, float, float]:
    return (value.x, value.y, value.z)


def _rigid(sphere: SphereBody, velocity: Vec3 | None = None) -> RigidBody:
    return RigidBody(
        sphere.body_id,
        _vec(sphere.position),
        _vec(sphere.velocity) if velocity is None else velocity,
        sphere.mass_kg,
        sphere.radius_m,
        sphere.restitution,
        sphere.friction,
        _vec(sphere.angular_velocity),
    )


def sphere_sphere_manifold(
    left: SphereBody, right: SphereBody, dt: float
) -> ContactManifold | None:
    """Continuous sphere pair via the existing linear sweep."""
    try:
        hit = sweep_spheres(_rigid(left), _rigid(right), delta_s=dt)
    except FrontierProductionError as exc:
        raise ContactRejected(str(exc)) from exc
    if hit is None:
        return None
    contact = hit.contact
    point = ManifoldPoint(
        _tup(contact.point),
        _tup(contact.normal_a_to_b),
        contact.penetration_m,
        "sphere",
    )
    return ContactManifold(
        hit.time_of_impact_s, (point,), hit.source, left.body_id, right.body_id
    )


def _box_minmax(box: BoxBody) -> tuple[Vec3, Vec3]:
    center = _vec(box.center)
    half = _vec(box.half_extents)
    return center - half, center + half


def _closest_point(center: Vec3, low: Vec3, high: Vec3) -> Vec3:
    return Vec3(
        min(max(center.x, low.x), high.x),
        min(max(center.y, low.y), high.y),
        min(max(center.z, low.z), high.z),
    )


def _unit(value: Vec3) -> Vec3:
    length = vecnorm(value)
    if length < 1e-12:
        raise ContactRejected("degenerate contact normal")
    return value.scaled(1.0 / length)


def _overlap_manifold(
    sphere: SphereBody,
    box: BoxBody,
) -> ContactManifold | None:
    center = _vec(sphere.position)
    low, high = _box_minmax(box)
    closest = _closest_point(center, low, high)
    delta = center - closest
    distance = vecnorm(delta)
    if distance > sphere.radius_m:
        return None
    if distance > 1e-8:
        outward = delta.scaled(1.0 / distance)
        penetration = sphere.radius_m - distance
    else:
        outward, penetration = _escape_axis(center, low, high, sphere.radius_m)
    normal = outward.scaled(-1.0)
    point = center + normal.scaled(sphere.radius_m)
    feature = (
        "face"
        if distance <= 1e-8 or _on_a_face(closest, low, high)
        else _feature_of(closest, low, high)
    )
    return ContactManifold(
        0.0,
        (ManifoldPoint(_tup(point), _tup(normal), penetration, feature),),
        "sphere_box_overlap",
        sphere.body_id,
        box.body_id,
    )


def _escape_axis(
    center: Vec3, low: Vec3, high: Vec3, radius: float
) -> tuple[Vec3, float]:
    candidates = (
        (high.x - center.x, Vec3(1.0, 0.0, 0.0)),
        (center.x - low.x, Vec3(-1.0, 0.0, 0.0)),
        (high.y - center.y, Vec3(0.0, 1.0, 0.0)),
        (center.y - low.y, Vec3(0.0, -1.0, 0.0)),
        (high.z - center.z, Vec3(0.0, 0.0, 1.0)),
        (center.z - low.z, Vec3(0.0, 0.0, -1.0)),
    )
    depth, outward = min(candidates, key=lambda item: item[0])
    return outward, depth + radius


def _on_a_face(point: Vec3, low: Vec3, high: Vec3) -> bool:
    on_x = abs(point.x - low.x) <= 1e-6 or abs(point.x - high.x) <= 1e-6
    on_y = abs(point.y - low.y) <= 1e-6 or abs(point.y - high.y) <= 1e-6
    on_z = abs(point.z - low.z) <= 1e-6 or abs(point.z - high.z) <= 1e-6
    return int(on_x) + int(on_y) + int(on_z) == 1


def _feature_of(point: Vec3, low: Vec3, high: Vec3) -> str:
    on_x = abs(point.x - low.x) <= 1e-5 or abs(point.x - high.x) <= 1e-5
    on_y = abs(point.y - low.y) <= 1e-5 or abs(point.y - high.y) <= 1e-5
    on_z = abs(point.z - low.z) <= 1e-5 or abs(point.z - high.z) <= 1e-5
    count = int(on_x) + int(on_y) + int(on_z)
    if count >= 3:
        return "vertex"
    if count == 2:
        return "edge"
    return "face"


def _roots(a: float, b: float, c: float, dt: float) -> tuple[float, ...]:
    if abs(a) < 1e-14:
        if abs(b) < 1e-14:
            return ()
        time = -c / b
        if -_TIME_TOLERANCE_S <= time <= dt + _TIME_TOLERANCE_S:
            return (max(0.0, time),)
        return ()
    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        return ()
    root = math.sqrt(discriminant)
    found = []
    for sign in (-1.0, 1.0):
        time = (-b + sign * root) / (2.0 * a)
        if -_TIME_TOLERANCE_S <= time <= dt + _TIME_TOLERANCE_S:
            found.append(max(0.0, time))
    return tuple(sorted(found))


def _on_rectangle(point: Vec3, face_point: Vec3, outward: Vec3, half: Vec3) -> bool:
    delta = point - face_point
    if abs(delta.dot(outward)) > 1e-4:
        return False
    if abs(outward.x) > 0.5:
        return (
            abs(delta.y) <= half.y + _FACE_TOLERANCE_M
            and abs(delta.z) <= half.z + _FACE_TOLERANCE_M
        )
    if abs(outward.y) > 0.5:
        return (
            abs(delta.x) <= half.x + _FACE_TOLERANCE_M
            and abs(delta.z) <= half.z + _FACE_TOLERANCE_M
        )
    return (
        abs(delta.x) <= half.x + _FACE_TOLERANCE_M
        and abs(delta.y) <= half.y + _FACE_TOLERANCE_M
    )


def _face_hits(
    sphere: SphereBody,
    box: BoxBody,
    relative: Vec3,
    dt: float,
) -> list[tuple[float, Vec3, str]]:
    center = _vec(box.center)
    half = _vec(box.half_extents)
    body = _rigid(sphere, relative)
    hits: list[tuple[float, Vec3, str]] = []
    axes = (Vec3(1.0, 0.0, 0.0), Vec3(0.0, 1.0, 0.0), Vec3(0.0, 0.0, 1.0))
    extents = (half.x, half.y, half.z)
    try:
        for axis, extent in zip(axes, extents):
            for sign in (1.0, -1.0):
                outward = axis.scaled(sign)
                face_point = center + outward.scaled(extent)
                swept = sweep_sphere_plane(
                    body,
                    plane_point=face_point,
                    plane_outward_normal=outward,
                    delta_s=dt,
                    surface_friction=box.friction,
                    surface_restitution=box.restitution,
                )
                if swept is None or swept.time_of_impact_s <= 1e-12:
                    continue
                if not _on_rectangle(swept.contact.point, face_point, outward, half):
                    continue
                hits.append((swept.time_of_impact_s, outward, "face"))
    except FrontierProductionError as exc:
        raise ContactRejected(str(exc)) from exc
    return hits


def _edge_hits(
    center: Vec3, relative: Vec3, radius: float, low: Vec3, high: Vec3, dt: float
) -> list[tuple[float, Vec3, str]]:
    corners_x = (low.x, high.x)
    corners_y = (low.y, high.y)
    corners_z = (low.z, high.z)
    segments: list[tuple[Vec3, Vec3]] = []
    for y in corners_y:
        for z in corners_z:
            segments.append((Vec3(low.x, y, z), Vec3(high.x, y, z)))
    for x in corners_x:
        for z in corners_z:
            segments.append((Vec3(x, low.y, z), Vec3(x, high.y, z)))
    for x in corners_x:
        for y in corners_y:
            segments.append((Vec3(x, y, low.z), Vec3(x, y, high.z)))
    hits: list[tuple[float, Vec3, str]] = []
    for start, end in segments:
        axis = end - start
        length = vecnorm(axis)
        if length < 1e-12:
            continue
        direction = axis.scaled(1.0 / length)
        offset = center - start
        initial = offset.cross(direction)
        velocity_term = relative.cross(direction)
        quadratic_a = velocity_term.dot(velocity_term)
        quadratic_b = 2.0 * initial.dot(velocity_term)
        quadratic_c = initial.dot(initial) - radius * radius
        for time in _roots(quadratic_a, quadratic_b, quadratic_c, dt):
            if time <= 1e-12:
                continue
            moved = offset + relative.scaled(time)
            parameter = moved.dot(direction)
            if parameter <= 1e-6 or parameter >= length - 1e-6:
                continue
            closest = start + direction.scaled(parameter)
            outward_raw = (center + relative.scaled(time)) - closest
            if vecnorm(outward_raw) < 1e-8:
                continue
            hits.append((time, _unit(outward_raw), "edge"))
    return hits


def _in_vertex_region(center: Vec3, corner: Vec3, low: Vec3, high: Vec3) -> bool:
    checks = (
        (
            abs(corner.x - high.x) <= 1e-8,
            center.x >= high.x - 1e-5,
            center.x <= low.x + 1e-5,
        ),
        (
            abs(corner.y - high.y) <= 1e-8,
            center.y >= high.y - 1e-5,
            center.y <= low.y + 1e-5,
        ),
        (
            abs(corner.z - high.z) <= 1e-8,
            center.z >= high.z - 1e-5,
            center.z <= low.z + 1e-5,
        ),
    )
    for at_max, outside_max, outside_min in checks:
        if at_max and not outside_max:
            return False
        if not at_max and not outside_min:
            return False
    return True


def _vertex_hits(
    center: Vec3, relative: Vec3, radius: float, low: Vec3, high: Vec3, dt: float
) -> list[tuple[float, Vec3, str]]:
    hits: list[tuple[float, Vec3, str]] = []
    for x in (low.x, high.x):
        for y in (low.y, high.y):
            for z in (low.z, high.z):
                corner = Vec3(x, y, z)
                offset = center - corner
                quadratic_a = relative.dot(relative)
                quadratic_b = 2.0 * offset.dot(relative)
                quadratic_c = offset.dot(offset) - radius * radius
                for time in _roots(quadratic_a, quadratic_b, quadratic_c, dt):
                    if time <= 1e-12:
                        continue
                    at = center + relative.scaled(time)
                    if not _in_vertex_region(at, corner, low, high):
                        continue
                    outward_raw = at - corner
                    if vecnorm(outward_raw) < 1e-8:
                        continue
                    hits.append((time, _unit(outward_raw), "vertex"))
    return hits


def sphere_box_manifold(
    sphere: SphereBody, box: BoxBody, dt: float
) -> ContactManifold | None:
    """Continuous sphere versus a translating AABB, one contact point."""
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise ContactRejected("dt must be a real number")
    step = float(dt)
    if math.isnan(step):
        raise ContactRejected("NaN")
    if step < 0.0 or step > 10.0:
        raise ContactRejected("dt out of range")
    overlap = _overlap_manifold(sphere, box)
    if overlap is not None:
        return overlap
    relative = _vec(sphere.velocity) - _vec(box.velocity)
    low, high = _box_minmax(box)
    center = _vec(sphere.position)
    candidates = []
    candidates.extend(_face_hits(sphere, box, relative, step))
    candidates.extend(_edge_hits(center, relative, sphere.radius_m, low, high, step))
    candidates.extend(_vertex_hits(center, relative, sphere.radius_m, low, high, step))
    if not candidates:
        return None
    feature_rank = {"face": 0, "edge": 1, "vertex": 2}
    time, outward, feature = min(
        candidates, key=lambda item: (item[0], feature_rank[item[2]])
    )
    frozen_center = center + relative.scaled(time)
    normal = outward.scaled(-1.0)
    frozen_point = frozen_center + normal.scaled(sphere.radius_m)
    world_point = frozen_point + _vec(box.velocity).scaled(time)
    return ContactManifold(
        time,
        (ManifoldPoint(_tup(world_point), _tup(normal), 0.0, feature),),
        "sphere_box_linear_ccd",
        sphere.body_id,
        box.body_id,
    )


def collision_contact(
    point: ManifoldPoint, friction: float, restitution: float
) -> CollisionContact:
    return CollisionContact(
        _vec(point.point),
        _vec(point.normal_a_to_b),
        point.penetration_m,
        friction,
        restitution,
    )
