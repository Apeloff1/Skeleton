"""Segmented mass, pose-aware center of mass, and animation retarget.

A body is a torso plus at least two limbs. Pose is a unit bone axis in the
parent frame. World endpoints are rebuilt from those axes and the stored bone
lengths, so a retarget cannot write free coordinates. The center of mass is
the mass-weighted average of the segment centers and must lie in their convex
hull. Contact impulses are applied to that rigid assembly; their vector sum is
the change in linear momentum. ``SegmentedRuntime.step`` assigns the new body
only after the scratch step returns.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from skeleton.frontier_contact.bodies import (
    BoxBody,
    SphereBody,
    _identifier,
    _range,
    _real,
    _vector,
)
from skeleton.frontier_contact.broadphase import broadphase_volumes
from skeleton.frontier_contact.errors import ContactRejected
from skeleton.frontier_contact.hull import point_in_convex_hull
from skeleton.frontier_contact.manifold import sphere_box_manifold
from skeleton.jeeves.game_frontier_advanced_physics import (
    AdvancedPhysicsError,
    Vec3,
    vecnorm,
)
from skeleton.jeeves.game_frontier_production import FrontierProductionError

_SOLVER_ERRORS = (
    AdvancedPhysicsError,
    FrontierProductionError,
    ZeroDivisionError,
    OverflowError,
)


def _unit_tuple(value: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2])
    if length < 1e-12:
        raise ContactRejected("bone axis must be a unit bone axis")
    return (value[0] / length, value[1] / length, value[2] / length)


@dataclass(frozen=True)
class MassSegment:
    name: str
    parent: int
    length_m: float
    mass_kg: float
    radius_m: float
    attach_to_parent_end: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _identifier(self.name, "segment name"))
        if (
            type(self.parent) is not int
            or isinstance(self.parent, bool)
            or self.parent < -1
        ):
            raise ContactRejected("invalid parent segment")
        object.__setattr__(
            self, "length_m", _range(self.length_m, "bone length", 0.001, 100.0)
        )
        mass = _real(self.mass_kg, "mass", limit=1_000_000.0)
        if mass < 0.0:
            raise ContactRejected("negative mass")
        if not 0.001 <= mass <= 1_000_000.0:
            raise ContactRejected("mass out of range")
        object.__setattr__(self, "mass_kg", mass)
        object.__setattr__(
            self, "radius_m", _range(self.radius_m, "radius", 0.001, 1000.0)
        )
        if not isinstance(self.attach_to_parent_end, bool):
            raise ContactRejected("attach flag must be boolean")


@dataclass(frozen=True)
class SegmentedBody:
    body_id: str
    root_position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    angular_velocity: tuple[float, float, float]
    segments: tuple[MassSegment, ...]
    local_axes: tuple[tuple[float, float, float], ...]
    restitution: float = 0.0
    friction: float = 0.6

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_id", _identifier(self.body_id, "body id"))
        object.__setattr__(
            self, "root_position", _vector(self.root_position, "root position")
        )
        object.__setattr__(self, "velocity", _vector(self.velocity, "velocity"))
        object.__setattr__(
            self, "angular_velocity", _vector(self.angular_velocity, "angular velocity")
        )
        if not isinstance(self.segments, tuple) or not self.segments:
            raise ContactRejected("segments required")
        if any(not isinstance(segment, MassSegment) for segment in self.segments):
            raise ContactRejected("segment required")
        if self.segments[0].parent != -1:
            raise ContactRejected("torso must be the root segment")
        if sum(segment.parent >= 0 for segment in self.segments) < 2:
            raise ContactRejected("at least two limb segments are required")
        names = [segment.name for segment in self.segments]
        if len(set(names)) != len(names):
            raise ContactRejected("duplicate segment name")
        for index, segment in enumerate(self.segments):
            if segment.parent >= index:
                raise ContactRejected("segment topology mismatch")
            if segment.parent < -1:
                raise ContactRejected("segment topology mismatch")
        if not isinstance(self.local_axes, tuple) or len(self.local_axes) != len(
            self.segments
        ):
            raise ContactRejected("segment count mismatch")
        axes = []
        for index, axis in enumerate(self.local_axes):
            components = _vector(axis, "bone axis")
            length = math.sqrt(
                components[0] ** 2 + components[1] ** 2 + components[2] ** 2
            )
            if not 1.0 - 1e-6 <= length <= 1.0 + 1e-6:
                raise ContactRejected("bone axis must be a unit bone axis")
            axes.append(components)
        object.__setattr__(self, "local_axes", tuple(axes))
        object.__setattr__(
            self, "restitution", _range(self.restitution, "restitution", 0.0, 1.0)
        )
        object.__setattr__(
            self, "friction", _range(self.friction, "friction", 0.0, 3.0)
        )
        for velocity in (self.velocity, self.angular_velocity):
            speed = math.sqrt(sum(component * component for component in velocity))
            if speed > 10_000.0:
                raise ContactRejected("speed bound exceeded")
        center_of_mass(self)


def _basis(axis: Vec3) -> tuple[Vec3, Vec3, Vec3]:
    reference = Vec3(1.0, 0.0, 0.0) if abs(axis.x) < 0.9 else Vec3(0.0, 1.0, 0.0)
    x_axis = axis.cross(reference)
    scale = vecnorm(x_axis)
    if scale < 1e-12:
        raise ContactRejected("degenerate bone basis")
    x_axis = x_axis.scaled(1.0 / scale)
    y_axis = axis.cross(x_axis)
    return x_axis, y_axis, axis


def world_axes(body: SegmentedBody) -> tuple[Vec3, ...]:
    axes: list[Vec3] = []
    for index, segment in enumerate(body.segments):
        local = Vec3(*body.local_axes[index])
        if segment.parent < 0:
            axes.append(local)
            continue
        parent = axes[segment.parent]
        x_axis, y_axis, z_axis = _basis(parent)
        axes.append(
            x_axis.scaled(local.x) + y_axis.scaled(local.y) + z_axis.scaled(local.z)
        )
    return tuple(axes)


def segment_endpoints(
    body: SegmentedBody,
) -> tuple[tuple[tuple[float, float, float], tuple[float, float, float]], ...]:
    """Head and tail rebuilt from bone length. Coordinates are not an input."""
    axes = world_axes(body)
    heads: list[Vec3] = []
    tails: list[Vec3] = []
    root = Vec3(*body.root_position)
    built = []
    for index, segment in enumerate(body.segments):
        if segment.parent < 0:
            head = root
        elif segment.attach_to_parent_end:
            head = tails[segment.parent]
        else:
            head = heads[segment.parent]
        tail = head + axes[index].scaled(segment.length_m)
        heads.append(head)
        tails.append(tail)
        built.append(((head.x, head.y, head.z), (tail.x, tail.y, tail.z)))
    return tuple(built)


def segment_centers(body: SegmentedBody) -> tuple[Vec3, ...]:
    centers = []
    for head, tail in segment_endpoints(body):
        centers.append(
            Vec3(
                0.5 * (head[0] + tail[0]),
                0.5 * (head[1] + tail[1]),
                0.5 * (head[2] + tail[2]),
            )
        )
    return tuple(centers)


def segment_mass_points(
    body: SegmentedBody,
) -> tuple[tuple[tuple[float, float, float], float], ...]:
    centers = segment_centers(body)
    return tuple(
        ((center.x, center.y, center.z), segment.mass_kg)
        for center, segment in zip(centers, body.segments)
    )


def center_of_mass(body: SegmentedBody) -> tuple[float, float, float]:
    """Pose-aware mass center. Raises when it leaves the segment hull."""
    points = segment_mass_points(body)
    total = sum(mass for _, mass in points)
    if total <= 0.0:
        raise ContactRejected("mass out of range")
    com = (
        sum(point[0] * mass for point, mass in points) / total,
        sum(point[1] * mass for point, mass in points) / total,
        sum(point[2] * mass for point, mass in points) / total,
    )
    cloud = tuple(point for point, _ in points)
    if not point_in_convex_hull(cloud, com, tol=1e-6):
        raise ContactRejected("center of mass outside hull")
    return com


def total_mass_kg(body: SegmentedBody) -> float:
    return sum(segment.mass_kg for segment in body.segments)


def pose_body(
    body: SegmentedBody,
    local_axes: tuple[tuple[float, float, float], ...],
) -> SegmentedBody:
    """Replace bone directions. Stored lengths are unchanged."""
    if len(local_axes) != len(body.segments):
        raise ContactRejected("segment count mismatch")
    return replace(body, local_axes=tuple(local_axes))


def retarget_animation(source: SegmentedBody, target: SegmentedBody) -> SegmentedBody:
    """Map source bone axes onto the target's segment count.

    Target bone lengths, masses, radii, names and topology stay on the target.
    The map is not a write of world endpoints.
    """
    if len(source.segments) != len(target.segments):
        raise ContactRejected("segment count mismatch")
    for origin, destination in zip(source.segments, target.segments):
        if (
            origin.parent != destination.parent
            or origin.attach_to_parent_end != destination.attach_to_parent_end
        ):
            raise ContactRejected("segment topology mismatch")
    return replace(target, local_axes=source.local_axes)


def place_body(
    body: SegmentedBody,
    root_position: tuple[float, float, float],
    velocity: tuple[float, float, float] | None = None,
    angular_velocity: tuple[float, float, float] | None = None,
) -> SegmentedBody:
    return replace(
        body,
        root_position=root_position,
        velocity=body.velocity if velocity is None else velocity,
        angular_velocity=body.angular_velocity
        if angular_velocity is None
        else angular_velocity,
    )


def _unit_axis_factory(x: float, y: float, z: float) -> tuple[float, float, float]:
    return _unit_tuple((x, y, z))


def standing_body() -> SegmentedBody:
    """Torso plus two legs. Lengths are the retarget reference, not a pose write."""
    segments = (
        MassSegment("torso", -1, 0.55, 32.0, 0.16, False),
        MassSegment("left_leg", 0, 0.42, 9.0, 0.07, False),
        MassSegment("right_leg", 0, 0.42, 9.0, 0.07, False),
    )
    axes = (
        (0.0, 0.0, 1.0),
        _unit_axis_factory(0.15, 0.45, -1.0),
        _unit_axis_factory(-0.15, -0.45, -1.0),
    )
    return SegmentedBody(
        "athlete",
        (0.0, 0.0, 0.55),
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0),
        segments,
        axes,
        0.0,
        0.6,
    )


def _mat_zero() -> list[list[float]]:
    return [[0.0, 0.0, 0.0] for _ in range(3)]


def inertia_about_com(body: SegmentedBody) -> tuple[tuple[float, float, float], ...]:
    com = Vec3(*center_of_mass(body))
    matrix = _mat_zero()
    for segment, center in zip(body.segments, segment_centers(body)):
        spin = 0.4 * segment.mass_kg * segment.radius_m * segment.radius_m
        for axis in range(3):
            matrix[axis][axis] += spin
        offset = center - com
        radius_sq = offset.dot(offset)
        components = (offset.x, offset.y, offset.z)
        for row in range(3):
            for column in range(3):
                kronecker = 1.0 if row == column else 0.0
                matrix[row][column] += segment.mass_kg * (
                    radius_sq * kronecker - components[row] * components[column]
                )
    return tuple(tuple(row) for row in matrix)


def _invert(
    matrix: tuple[tuple[float, float, float], ...],
) -> tuple[tuple[float, float, float], ...]:
    a, b, c = matrix
    det = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    if not math.isfinite(det) or abs(det) < 1e-14:
        raise ContactRejected("singular inertia")
    inv = 1.0 / det
    return (
        (
            (b[1] * c[2] - b[2] * c[1]) * inv,
            (a[2] * c[1] - a[1] * c[2]) * inv,
            (a[1] * b[2] - a[2] * b[1]) * inv,
        ),
        (
            (b[2] * c[0] - b[0] * c[2]) * inv,
            (a[0] * c[2] - a[2] * c[0]) * inv,
            (a[2] * b[0] - a[0] * b[2]) * inv,
        ),
        (
            (b[0] * c[1] - b[1] * c[0]) * inv,
            (a[1] * c[0] - a[0] * c[1]) * inv,
            (a[0] * b[1] - a[1] * b[0]) * inv,
        ),
    )


def _mul(matrix: tuple[tuple[float, float, float], ...], vector: Vec3) -> Vec3:
    return Vec3(
        matrix[0][0] * vector.x + matrix[0][1] * vector.y + matrix[0][2] * vector.z,
        matrix[1][0] * vector.x + matrix[1][1] * vector.y + matrix[1][2] * vector.z,
        matrix[2][0] * vector.x + matrix[2][1] * vector.y + matrix[2][2] * vector.z,
    )


def _rotate(vector: Vec3, omega: Vec3, dt: float) -> Vec3:
    angle = vecnorm(omega) * dt
    if angle < 1e-12:
        return vector + omega.cross(vector).scaled(dt)
    axis = omega.scaled(1.0 / vecnorm(omega))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        vector.scaled(cosine)
        + axis.cross(vector).scaled(sine)
        + axis.scaled(axis.dot(vector) * (1.0 - cosine))
    )


def _integrate(body: SegmentedBody, dt: float) -> SegmentedBody:
    if dt == 0.0:
        return body
    com = Vec3(*center_of_mass(body))
    velocity = Vec3(*body.velocity)
    omega = Vec3(*body.angular_velocity)
    root = Vec3(*body.root_position)
    new_root = com + velocity.scaled(dt) + _rotate(root - com, omega, dt)
    axes = list(body.local_axes)
    rotated = _rotate(world_axes(body)[0], omega, dt)
    scale = vecnorm(rotated)
    if scale < 1e-12:
        raise ContactRejected("degenerate bone basis")
    rotated = rotated.scaled(1.0 / scale)
    axes[0] = (rotated.x, rotated.y, rotated.z)
    return replace(
        body, root_position=(new_root.x, new_root.y, new_root.z), local_axes=tuple(axes)
    )


def _translate(body: SegmentedBody, delta: Vec3) -> SegmentedBody:
    root = Vec3(*body.root_position) + delta
    return replace(body, root_position=(root.x, root.y, root.z))


@dataclass(frozen=True)
class PointImpulse:
    segment: str
    impulse_ns: tuple[float, float, float]
    normal_impulse_ns: float
    friction_impulse_ns: float
    normal: tuple[float, float, float]


@dataclass(frozen=True)
class _Hit:
    segment_index: int
    toi: float
    point: Vec3
    normal_up: Vec3
    penetration: float


def _probe(body: SegmentedBody, index: int) -> SphereBody:
    center = segment_centers(body)[index]
    segment = body.segments[index]
    com = Vec3(*center_of_mass(body))
    velocity = Vec3(*body.velocity) + Vec3(*body.angular_velocity).cross(center - com)
    return SphereBody(
        f"{body.body_id}:{segment.name}",
        (center.x, center.y, center.z),
        (velocity.x, velocity.y, velocity.z),
        segment.mass_kg,
        segment.radius_m,
        body.restitution,
        body.friction,
        body.angular_velocity,
    )


def _collect(
    body: SegmentedBody, ground: BoxBody, dt: float, cell_size_m: float
) -> tuple[_Hit, ...]:
    probes = tuple(_probe(body, index) for index in range(len(body.segments)))
    _, pairs = broadphase_volumes(probes, (ground,), dt, cell_size_m=cell_size_m)
    com = Vec3(*center_of_mass(body))
    velocity = Vec3(*body.velocity)
    omega = Vec3(*body.angular_velocity)
    ground_velocity = Vec3(*ground.velocity)
    found: list[_Hit] = []
    seen: set[int] = set()
    for left, right in pairs:
        if right != len(probes) and left != len(probes):
            continue
        segment_index = left if left < len(probes) else right
        if segment_index in seen:
            continue
        manifold = sphere_box_manifold(probes[segment_index], ground, dt)
        if manifold is None:
            continue
        point = manifold.points[0]
        normal_up = Vec3(*point.normal_a_to_b).scaled(-1.0)
        contact = Vec3(*point.point)
        relative = velocity + omega.cross(contact - com) - ground_velocity
        approaching = relative.dot(normal_up) < -1e-8
        if manifold.time_of_impact_s > 1e-12 and not approaching:
            continue
        if (
            manifold.time_of_impact_s <= 1e-12
            and not approaching
            and point.penetration_m <= 1e-6
        ):
            continue
        seen.add(segment_index)
        found.append(
            _Hit(
                segment_index,
                manifold.time_of_impact_s,
                contact,
                normal_up,
                point.penetration_m,
            )
        )
    return tuple(
        sorted(
            found,
            key=lambda hit: (
                hit.toi,
                hit.segment_index,
                body.segments[hit.segment_index].name,
            ),
        )
    )


def _apply_hit(
    body: SegmentedBody,
    hit: _Hit,
    ground: BoxBody,
    inverse_inertia: tuple[tuple[float, float, float], ...],
) -> tuple[SegmentedBody, PointImpulse | None]:
    mass = total_mass_kg(body)
    inv_mass = 1.0 / mass
    com = Vec3(*center_of_mass(body))
    velocity = Vec3(*body.velocity)
    omega = Vec3(*body.angular_velocity)
    normal = hit.normal_up
    lever = hit.point - com
    ground_velocity = Vec3(*ground.velocity)
    relative = velocity + omega.cross(lever) - ground_velocity
    normal_speed = relative.dot(normal)
    lever_normal = lever.cross(normal)
    denom = inv_mass + lever_normal.dot(_mul(inverse_inertia, lever_normal))
    if denom < 1e-12:
        raise ContactRejected("degenerate contact mass")
    restitution = min(body.restitution, ground.restitution)
    normal_impulse = 0.0
    if normal_speed < 0.0:
        normal_impulse = -(1.0 + restitution) * normal_speed / denom
    impulse = normal.scaled(normal_impulse)
    velocity = velocity + impulse.scaled(inv_mass)
    omega = omega + _mul(inverse_inertia, lever.cross(impulse))
    friction_impulse = 0.0
    if normal_impulse > 0.0:
        relative = velocity + omega.cross(lever) - ground_velocity
        tangent_velocity = relative - normal.scaled(relative.dot(normal))
        tangent_speed = vecnorm(tangent_velocity)
        if tangent_speed > 1e-9:
            tangent = tangent_velocity.scaled(1.0 / tangent_speed)
            lever_tangent = lever.cross(tangent)
            tangent_denom = inv_mass + lever_tangent.dot(
                _mul(inverse_inertia, lever_tangent)
            )
            if tangent_denom < 1e-12:
                raise ContactRejected("degenerate contact mass")
            mu = math.sqrt(body.friction * ground.friction)
            friction_impulse = min(tangent_speed / tangent_denom, mu * normal_impulse)
            friction = tangent.scaled(-friction_impulse)
            impulse = impulse + friction
            velocity = velocity + friction.scaled(inv_mass)
            omega = omega + _mul(inverse_inertia, lever.cross(friction))
    updated = replace(
        body,
        velocity=(velocity.x, velocity.y, velocity.z),
        angular_velocity=(omega.x, omega.y, omega.z),
    )
    if normal_impulse <= 0.0 and friction_impulse <= 0.0:
        return updated, None
    return updated, PointImpulse(
        body.segments[hit.segment_index].name,
        (impulse.x, impulse.y, impulse.z),
        normal_impulse,
        friction_impulse,
        (normal.x, normal.y, normal.z),
    )


def _separate(body: SegmentedBody, hits: tuple[_Hit, ...]) -> SegmentedBody:
    if not hits:
        return body
    deepest = max(hits, key=lambda hit: hit.penetration)
    if deepest.penetration <= 1e-6:
        return body
    return _translate(body, deepest.normal_up.scaled(deepest.penetration * 0.8))


@dataclass(frozen=True)
class SegmentedStepResult:
    body: SegmentedBody
    impulses: tuple[PointImpulse, ...]
    center_of_mass: tuple[float, float, float]
    iterations_used: int


def step_segmented(
    body: SegmentedBody,
    dt: float,
    ground: BoxBody,
    *,
    pose_source: SegmentedBody | None = None,
    iteration_cap: int = 8,
    cell_size_m: float = 1.0,
) -> SegmentedStepResult:
    """Retarget on a scratch copy, then solve multipoint contacts.

    ``dt`` is validated after a candidate retarget is built. A later rejection
    discards that copy; the caller's body is not replaced by this function.
    """
    if not isinstance(body, SegmentedBody):
        raise ContactRejected("segmented body required")
    scratch = body if pose_source is None else retarget_animation(pose_source, body)
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise ContactRejected("dt must be a real number")
    step = float(dt)
    if math.isnan(step):
        raise ContactRejected("NaN")
    if not math.isfinite(step) or step < 0.0 or step > 10.0:
        raise ContactRejected("dt out of range")
    if type(iteration_cap) is not int or iteration_cap < 1:
        raise ContactRejected("iteration cap must be a positive integer")
    if not isinstance(ground, BoxBody):
        raise ContactRejected("box required")
    if ground.body_id == scratch.body_id:
        raise ContactRejected("duplicate body id")
    try:
        return _solve(scratch, step, ground, iteration_cap, cell_size_m)
    except ContactRejected:
        raise
    except _SOLVER_ERRORS as exc:
        raise ContactRejected(str(exc)) from exc


def _solve(
    body: SegmentedBody,
    dt: float,
    ground: BoxBody,
    iteration_cap: int,
    cell_size_m: float,
) -> SegmentedStepResult:
    scratch = body
    records: list[PointImpulse] = []
    consumed = 0.0
    used = 0
    for iteration in range(iteration_cap):
        remaining = dt - consumed
        if remaining <= 1e-12:
            break
        active = _collect(scratch, ground, remaining, cell_size_m)
        if not active:
            scratch = _integrate(scratch, remaining)
            consumed = dt
            break
        used = iteration + 1
        earliest = min(hit.toi for hit in active)
        if earliest > 1e-12:
            scratch = _integrate(scratch, earliest)
            consumed += earliest
            active = tuple(
                hit
                for hit in _collect(
                    scratch, ground, max(0.0, dt - consumed), cell_size_m
                )
                if hit.toi <= 1e-4 or hit.penetration > 1e-6
            )
            if not active:
                continue
        inverse = _invert(inertia_about_com(scratch))
        applied = False
        for hit in active:
            scratch, record = _apply_hit(scratch, hit, ground, inverse)
            if record is not None:
                records.append(record)
                applied = True
        if applied:
            continue
        scratch = _separate(scratch, active)
        leftover = dt - consumed
        still = (
            _collect(scratch, ground, leftover, cell_size_m) if leftover > 1e-12 else ()
        )
        if any(hit.toi <= 1e-5 and hit.penetration > 1e-5 for hit in still):
            break
        if leftover > 1e-12:
            scratch = _integrate(scratch, leftover)
            consumed = dt
        break
    else:
        leftover = dt - consumed
        if leftover > 1e-12 and not _collect(scratch, ground, leftover, cell_size_m):
            scratch = _integrate(scratch, leftover)
    return SegmentedStepResult(scratch, tuple(records), center_of_mass(scratch), used)


class SegmentedRuntime:
    """Commits a segmented body only when the full step returns."""

    def __init__(self, body: SegmentedBody) -> None:
        if not isinstance(body, SegmentedBody):
            raise ContactRejected("segmented body required")
        self._body = body

    @property
    def body(self) -> SegmentedBody:
        return self._body

    def step(
        self,
        dt: float,
        ground: BoxBody,
        *,
        pose_source: SegmentedBody | None = None,
        iteration_cap: int = 8,
        cell_size_m: float = 1.0,
    ) -> SegmentedStepResult:
        prior = self._body
        try:
            result = step_segmented(
                prior,
                dt,
                ground,
                pose_source=pose_source,
                iteration_cap=iteration_cap,
                cell_size_m=cell_size_m,
            )
        except ContactRejected:
            self._body = prior
            raise
        self._body = result.body
        return result
