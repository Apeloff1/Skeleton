"""Deterministic kinematic capsule character movement.

The controller is a query/response layer over the physics world. It never mutates
other bodies. Movement uses continuous capsule casts, start-state depenetration,
slope-aware sliding, ground snapping, and a bounded step-up attempt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .body import RigidBody
from .collision import ContactManifold, detect_collision
from .convex import gjk_distance
from .errors import PhysicsValidationError, UnsupportedCollisionError
from .math3d import EPSILON, AABB, Quat, Transform, Vec3
from .mesh import TriangleMeshShape, closest_points_segment_triangle
from .shapes import (
    CapsuleShape,
    PlaneShape,
)

if TYPE_CHECKING:
    from .world import PhysicsWorld

MAX_CHARACTER_ITERATIONS = 64
MAX_CHARACTER_CAST_ITERATIONS = 128
_CHARACTER_EPSILON = 1.0e-9


def _finite_non_negative(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise PhysicsValidationError(
            f"{name} must be finite and non-negative"
        )
    return value


def _finite_positive(value: float, *, name: str) -> float:
    value = _finite_non_negative(value, name=name)
    if value <= 0.0:
        raise PhysicsValidationError(f"{name} must be positive")
    return value


def _bounded_int(value: int, *, name: str, maximum: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= maximum
    ):
        raise PhysicsValidationError(
            f"{name} outside supported range"
        )
    return value


def _orientation_from_up(up: Vec3) -> Quat:
    local_up = Vec3.axis(1)
    dot = max(-1.0, min(1.0, local_up.dot(up)))
    if dot >= 1.0 - 1.0e-12:
        return Quat.identity()
    if dot <= -1.0 + 1.0e-12:
        return Quat.from_axis_angle(Vec3.axis(0), math.pi)
    axis = local_up.cross(up).normalized()
    return Quat.from_axis_angle(axis, math.acos(dot))


@dataclass(frozen=True, slots=True)
class CapsuleCastHit:
    body_id: str
    fraction: float
    distance: float
    point: Vec3
    normal: Vec3
    triangle_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.body_id, str) or not self.body_id:
            raise PhysicsValidationError(
                "capsule cast body_id must be non-empty"
            )
        if (
            not math.isfinite(self.fraction)
            or not 0.0 <= self.fraction <= 1.0
        ):
            raise PhysicsValidationError(
                "capsule cast fraction must be in [0, 1]"
            )
        if not math.isfinite(self.distance) or self.distance < 0.0:
            raise PhysicsValidationError(
                "capsule cast distance must be finite and non-negative"
            )
        if not isinstance(self.point, Vec3):
            raise PhysicsValidationError(
                "capsule cast point must be Vec3"
            )
        object.__setattr__(self, "normal", self.normal.normalized())
        if self.triangle_index is not None and (
            isinstance(self.triangle_index, bool)
            or not isinstance(self.triangle_index, int)
            or self.triangle_index < 0
        ):
            raise PhysicsValidationError(
                "capsule cast triangle_index must be non-negative"
            )


@dataclass(frozen=True, slots=True)
class CharacterControllerSettings:
    radius: float = 0.4
    half_height: float = 0.8
    up: Vec3 = Vec3(0.0, 1.0, 0.0)
    skin_width: float = 0.02
    max_slope_degrees: float = 50.0
    step_height: float = 0.3
    ground_snap_distance: float = 0.15
    max_iterations: int = 8
    cast_iterations: int = 32
    minimum_move_distance: float = 1.0e-5

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "radius",
            _finite_positive(self.radius, name="radius"),
        )
        object.__setattr__(
            self,
            "half_height",
            _finite_positive(self.half_height, name="half_height"),
        )
        if not isinstance(self.up, Vec3):
            raise PhysicsValidationError("up must be Vec3")
        object.__setattr__(self, "up", self.up.normalized())
        object.__setattr__(
            self,
            "skin_width",
            _finite_non_negative(
                self.skin_width,
                name="skin_width",
            ),
        )
        slope = _finite_non_negative(
            self.max_slope_degrees,
            name="max_slope_degrees",
        )
        if slope >= 90.0:
            raise PhysicsValidationError(
                "max_slope_degrees must be less than 90"
            )
        object.__setattr__(self, "max_slope_degrees", slope)
        object.__setattr__(
            self,
            "step_height",
            _finite_non_negative(
                self.step_height,
                name="step_height",
            ),
        )
        object.__setattr__(
            self,
            "ground_snap_distance",
            _finite_non_negative(
                self.ground_snap_distance,
                name="ground_snap_distance",
            ),
        )
        object.__setattr__(
            self,
            "minimum_move_distance",
            _finite_positive(
                self.minimum_move_distance,
                name="minimum_move_distance",
            ),
        )
        _bounded_int(
            self.max_iterations,
            name="max_iterations",
            maximum=MAX_CHARACTER_ITERATIONS,
        )
        _bounded_int(
            self.cast_iterations,
            name="cast_iterations",
            maximum=MAX_CHARACTER_CAST_ITERATIONS,
        )

    @property
    def walkable_normal_dot(self) -> float:
        return math.cos(math.radians(self.max_slope_degrees))

    @property
    def orientation(self) -> Quat:
        return _orientation_from_up(self.up)

    @property
    def shape(self) -> CapsuleShape:
        return CapsuleShape(self.radius, self.half_height)


@dataclass(frozen=True, slots=True)
class CharacterMoveResult:
    start_position: Vec3
    position: Vec3
    requested_displacement: Vec3
    actual_displacement: Vec3
    remaining_displacement: Vec3
    hits: tuple[CapsuleCastHit, ...]
    grounded: bool
    ground_normal: Vec3 | None
    ground_body: str | None
    stepped: bool
    iterations: int

    def __post_init__(self) -> None:
        if self.grounded:
            if self.ground_normal is None or self.ground_body is None:
                raise PhysicsValidationError(
                    "grounded character requires ground contact"
                )
        elif self.ground_normal is not None or self.ground_body is not None:
            raise PhysicsValidationError(
                "ungrounded character cannot carry ground contact"
            )


def _probe_id(world: "PhysicsWorld") -> str:
    existing = {body.body_id for body in world.bodies()}
    base = "character-probe"
    if base not in existing:
        return base
    for index in range(1, 1_000_000):
        candidate = f"{base}-{index}"
        if candidate not in existing:
            return candidate
    raise PhysicsValidationError(
        "unable to allocate deterministic character probe id"
    )


def _probe_body(
    probe_id: str,
    settings: CharacterControllerSettings,
    position: Vec3,
) -> RigidBody:
    return RigidBody.static(
        probe_id,
        settings.shape,
        position=position,
        orientation=settings.orientation,
    )


def _finite_convex_target(body: RigidBody) -> bool:
    return not isinstance(body.shape, (PlaneShape, TriangleMeshShape))


def _cast_plane(
    settings: CharacterControllerSettings,
    position: Vec3,
    displacement: Vec3,
    target: RigidBody,
) -> CapsuleCastHit | None:
    shape = target.shape
    assert isinstance(shape, PlaneShape)
    normal, offset = shape.world_equation(target.transform)
    transform = Transform(position, settings.orientation)
    deepest = settings.shape.support(-normal, transform)
    signed_gap = (
        normal.dot(deepest)
        - offset
        - settings.skin_width
    )
    closing = -displacement.dot(normal)

    if signed_gap <= 0.0:
        if closing <= _CHARACTER_EPSILON:
            return None
        point = deepest - normal * (
            normal.dot(deepest) - offset
        )
        return CapsuleCastHit(
            target.body_id,
            0.0,
            0.0,
            point,
            normal,
        )
    if closing <= _CHARACTER_EPSILON:
        return None

    fraction = signed_gap / closing
    if fraction < 0.0 or fraction > 1.0:
        return None
    fraction = min(1.0, max(0.0, fraction))
    hit_deepest = deepest + displacement * fraction
    point = hit_deepest - normal * settings.skin_width
    return CapsuleCastHit(
        target.body_id,
        fraction,
        displacement.length() * fraction,
        point,
        normal,
    )


def _cast_convex(
    probe_id: str,
    settings: CharacterControllerSettings,
    position: Vec3,
    displacement: Vec3,
    target: RigidBody,
) -> CapsuleCastHit | None:
    fraction = 0.0
    last_point = position
    last_normal = Vec3.zero()

    for _ in range(settings.cast_iterations):
        probe_position = position + displacement * fraction
        probe = _probe_body(probe_id, settings, probe_position)
        result = gjk_distance(
            probe,
            target,
            max_iterations=64,
            tolerance=max(
                1.0e-10,
                settings.skin_width * 1.0e-4,
            ),
        )

        if result.intersects:
            manifold: ContactManifold | None
            try:
                manifold = detect_collision(target, probe)
            except UnsupportedCollisionError:
                manifold = None
            if manifold is not None:
                normal = manifold.normal
                point = manifold.points[0].position
            else:
                normal = (
                    -last_normal
                    if last_normal.length_squared() > EPSILON * EPSILON
                    else (probe_position - target.position).normalized_or_zero()
                )
                if normal.length_squared() <= EPSILON * EPSILON:
                    normal = -displacement.normalized_or_zero()
                if normal.length_squared() <= EPSILON * EPSILON:
                    normal = settings.up
                point = probe_position

            if displacement.dot(normal) >= -_CHARACTER_EPSILON:
                return None
            return CapsuleCastHit(
                target.body_id,
                fraction,
                displacement.length() * fraction,
                point,
                normal,
            )

        last_point = result.point_b
        last_normal = result.normal
        gap = result.distance - settings.skin_width
        obstacle_normal = -result.normal
        if gap <= _CHARACTER_EPSILON:
            if displacement.dot(obstacle_normal) >= -_CHARACTER_EPSILON:
                return None
            return CapsuleCastHit(
                target.body_id,
                fraction,
                displacement.length() * fraction,
                result.point_b,
                obstacle_normal,
            )

        closing = displacement.dot(result.normal)
        if closing <= _CHARACTER_EPSILON:
            return None
        advance = gap / closing
        if advance <= 1.0e-12:
            raise PhysicsValidationError(
                "character convex cast failed to make progress"
            )
        fraction += advance
        if fraction > 1.0:
            return None

    raise PhysicsValidationError(
        "character convex cast iteration bound exceeded"
    )


def _mesh_segment_at(
    mesh: RigidBody,
    settings: CharacterControllerSettings,
    position: Vec3,
) -> tuple[Vec3, Vec3]:
    transform = Transform(position, settings.orientation)
    first, second = settings.shape.segment_endpoints(transform)
    return (
        mesh.transform.inverse_transform_point(first),
        mesh.transform.inverse_transform_point(second),
    )


def _cast_mesh_triangle(
    mesh: RigidBody,
    settings: CharacterControllerSettings,
    position: Vec3,
    displacement: Vec3,
    triangle_index: int,
) -> CapsuleCastHit | None:
    shape = mesh.shape
    assert isinstance(shape, TriangleMeshShape)
    local_displacement = mesh.transform.inverse_transform_vector(
        displacement
    )
    first, second = _mesh_segment_at(mesh, settings, position)
    a, b, c = shape.triangle_vertices(triangle_index)
    fraction = 0.0
    last_normal = Vec3.zero()

    for _ in range(settings.cast_iterations):
        offset = local_displacement * fraction
        closest = closest_points_segment_triangle(
            first + offset,
            second + offset,
            a,
            b,
            c,
        )
        delta = closest.segment_point - closest.triangle_point
        distance = math.sqrt(max(0.0, delta.length_squared()))
        gap = distance - settings.radius - settings.skin_width

        if distance > _CHARACTER_EPSILON:
            normal_local = delta / distance
        else:
            normal_local = shape.triangle_normal(triangle_index)
            midpoint = (
                first + second
            ) * 0.5 + offset
            if normal_local.dot(midpoint - a) < 0.0:
                normal_local = -normal_local

        obstacle_normal = mesh.transform.transform_vector(
            normal_local
        ).normalized()
        last_normal = obstacle_normal
        if gap <= _CHARACTER_EPSILON:
            if (
                displacement.dot(obstacle_normal)
                >= -_CHARACTER_EPSILON
            ):
                return None
            point = mesh.transform.transform_point(
                closest.triangle_point
            )
            return CapsuleCastHit(
                mesh.body_id,
                fraction,
                displacement.length() * fraction,
                point,
                obstacle_normal,
                triangle_index,
            )

        closing = -local_displacement.dot(normal_local)
        if closing <= _CHARACTER_EPSILON:
            return None
        advance = gap / closing
        if advance <= 1.0e-12:
            raise PhysicsValidationError(
                "character mesh cast failed to make progress"
            )
        fraction += advance
        if fraction > 1.0:
            return None

    if last_normal.length_squared() > EPSILON * EPSILON:
        raise PhysicsValidationError(
            "character mesh cast iteration bound exceeded"
        )
    return None


def _cast_mesh(
    settings: CharacterControllerSettings,
    position: Vec3,
    displacement: Vec3,
    mesh: RigidBody,
) -> CapsuleCastHit | None:
    shape = mesh.shape
    assert isinstance(shape, TriangleMeshShape)
    start_first, start_second = _mesh_segment_at(
        mesh,
        settings,
        position,
    )
    local_displacement = mesh.transform.inverse_transform_vector(
        displacement
    )
    end_first = start_first + local_displacement
    end_second = start_second + local_displacement
    extent = Vec3.one() * (
        settings.radius + settings.skin_width
    )
    swept_bounds = AABB(
        start_first.min(start_second).min(end_first).min(end_second)
        - extent,
        start_first.max(start_second).max(end_first).max(end_second)
        + extent,
    )

    hits = [
        hit
        for triangle_index in shape.candidate_triangles(swept_bounds)
        if (
            hit := _cast_mesh_triangle(
                mesh,
                settings,
                position,
                displacement,
                triangle_index,
            )
        )
        is not None
    ]
    if not hits:
        return None
    return min(
        hits,
        key=lambda hit: (
            hit.fraction,
            hit.triangle_index
            if hit.triangle_index is not None
            else -1,
        ),
    )


def capsule_cast_body(
    probe_id: str,
    settings: CharacterControllerSettings,
    position: Vec3,
    displacement: Vec3,
    target: RigidBody,
) -> CapsuleCastHit | None:
    if not isinstance(position, Vec3) or not isinstance(displacement, Vec3):
        raise PhysicsValidationError(
            "character cast position/displacement must be Vec3"
        )
    if displacement.length_squared() <= _CHARACTER_EPSILON**2:
        return None
    if isinstance(target.shape, PlaneShape):
        return _cast_plane(
            settings,
            position,
            displacement,
            target,
        )
    if isinstance(target.shape, TriangleMeshShape):
        return _cast_mesh(
            settings,
            position,
            displacement,
            target,
        )
    if _finite_convex_target(target):
        return _cast_convex(
            probe_id,
            settings,
            position,
            displacement,
            target,
        )
    raise UnsupportedCollisionError(
        f"unsupported character cast target: {target.shape.kind.value}"
    )


def capsule_cast_world(
    world: "PhysicsWorld",
    settings: CharacterControllerSettings,
    position: Vec3,
    displacement: Vec3,
    *,
    ignore: tuple[str, ...] = (),
) -> CapsuleCastHit | None:
    probe_id = _probe_id(world)
    ignored = set(ignore)
    hits: list[CapsuleCastHit] = []
    for body in world.bodies():
        if body.body_id in ignored:
            continue
        hit = capsule_cast_body(
            probe_id,
            settings,
            position,
            displacement,
            body,
        )
        if hit is not None:
            hits.append(hit)
    if not hits:
        return None
    return min(
        hits,
        key=lambda hit: (
            hit.fraction,
            hit.body_id,
            -1 if hit.triangle_index is None else hit.triangle_index,
        ),
    )


class KinematicCharacterController:
    def __init__(
        self,
        settings: CharacterControllerSettings | None = None,
    ) -> None:
        if settings is not None and not isinstance(
            settings,
            CharacterControllerSettings,
        ):
            raise PhysicsValidationError(
                "character settings must be CharacterControllerSettings"
            )
        self.settings = settings or CharacterControllerSettings()

    def _walkable(self, normal: Vec3) -> bool:
        return (
            normal.dot(self.settings.up)
            >= self.settings.walkable_normal_dot
        )

    def _depenetrate(
        self,
        world: "PhysicsWorld",
        position: Vec3,
        *,
        ignore: tuple[str, ...],
    ) -> tuple[Vec3, tuple[CapsuleCastHit, ...]]:
        probe_id = _probe_id(world)
        ignored = set(ignore)
        hits: list[CapsuleCastHit] = []
        current = position

        for _ in range(self.settings.max_iterations):
            probe = _probe_body(
                probe_id,
                self.settings,
                current,
            )
            overlaps: list[tuple[float, str, ContactManifold]] = []
            for body in world.bodies():
                if body.body_id in ignored:
                    continue
                try:
                    manifold = detect_collision(body, probe)
                except UnsupportedCollisionError:
                    continue
                if manifold is None or manifold.penetration <= 0.0:
                    continue
                overlaps.append(
                    (
                        manifold.penetration,
                        body.body_id,
                        manifold,
                    )
                )
            if not overlaps:
                break

            penetration, body_id, manifold = sorted(
                overlaps,
                key=lambda row: (
                    -row[0],
                    row[1],
                ),
            )[0]
            normal = manifold.normal
            push = penetration + self.settings.skin_width
            current = current + normal * push
            hits.append(
                CapsuleCastHit(
                    body_id,
                    0.0,
                    0.0,
                    manifold.points[0].position,
                    normal,
                )
            )
        else:
            raise PhysicsValidationError(
                "character depenetration iteration bound exceeded"
            )

        return current, tuple(hits)

    def _ground_probe(
        self,
        world: "PhysicsWorld",
        position: Vec3,
        *,
        ignore: tuple[str, ...],
    ) -> CapsuleCastHit | None:
        if self.settings.ground_snap_distance <= 0.0:
            return None
        hit = capsule_cast_world(
            world,
            self.settings,
            position,
            -self.settings.up * self.settings.ground_snap_distance,
            ignore=ignore,
        )
        if hit is None or not self._walkable(hit.normal):
            return None
        return hit

    def _try_step(
        self,
        world: "PhysicsWorld",
        position: Vec3,
        remaining: Vec3,
        *,
        ignore: tuple[str, ...],
    ) -> tuple[Vec3, CapsuleCastHit] | None:
        if self.settings.step_height <= 0.0:
            return None

        up_move = self.settings.up * self.settings.step_height
        up_hit = capsule_cast_world(
            world,
            self.settings,
            position,
            up_move,
            ignore=ignore,
        )
        if up_hit is not None:
            return None
        elevated = position + up_move

        horizontal = (
            remaining
            - self.settings.up * remaining.dot(self.settings.up)
        )
        if (
            horizontal.length_squared()
            <= self.settings.minimum_move_distance**2
        ):
            return None

        forward_hit = capsule_cast_world(
            world,
            self.settings,
            elevated,
            horizontal,
            ignore=ignore,
        )
        if forward_hit is None:
            advanced = elevated + horizontal
        else:
            if forward_hit.fraction <= _CHARACTER_EPSILON:
                return None
            advanced = elevated + horizontal * forward_hit.fraction

        down_distance = (
            self.settings.step_height
            + self.settings.ground_snap_distance
        )
        down = -self.settings.up * down_distance
        down_hit = capsule_cast_world(
            world,
            self.settings,
            advanced,
            down,
            ignore=ignore,
        )
        if down_hit is None or not self._walkable(down_hit.normal):
            return None

        stepped_position = advanced + down * down_hit.fraction
        return stepped_position, down_hit

    def move(
        self,
        world: "PhysicsWorld",
        position: Vec3,
        displacement: Vec3,
        *,
        ignore: tuple[str, ...] = (),
    ) -> CharacterMoveResult:
        if not isinstance(position, Vec3) or not isinstance(displacement, Vec3):
            raise PhysicsValidationError(
                "character position/displacement must be Vec3"
            )

        start = position
        position, depenetration_hits = self._depenetrate(
            world,
            position,
            ignore=ignore,
        )
        hits = list(depenetration_hits)
        remaining = displacement
        ground_hit = self._ground_probe(
            world,
            position,
            ignore=ignore,
        )
        grounded = ground_hit is not None
        ground_normal = None if ground_hit is None else ground_hit.normal
        ground_body = None if ground_hit is None else ground_hit.body_id
        stepped = False
        iterations = 0

        for iterations in range(1, self.settings.max_iterations + 1):
            if (
                remaining.length_squared()
                <= self.settings.minimum_move_distance**2
            ):
                remaining = Vec3.zero()
                break

            hit = capsule_cast_world(
                world,
                self.settings,
                position,
                remaining,
                ignore=ignore,
            )
            if hit is None:
                position = position + remaining
                remaining = Vec3.zero()
                break

            hits.append(hit)
            fraction = min(1.0, max(0.0, hit.fraction))
            position = position + remaining * fraction
            after = remaining * (1.0 - fraction)

            walkable = self._walkable(hit.normal)
            if walkable:
                grounded = True
                ground_normal = hit.normal
                ground_body = hit.body_id
            elif grounded and not stepped:
                step = self._try_step(
                    world,
                    position,
                    after,
                    ignore=ignore,
                )
                if step is not None:
                    position, step_ground = step
                    hits.append(step_ground)
                    grounded = True
                    ground_normal = step_ground.normal
                    ground_body = step_ground.body_id
                    stepped = True
                    remaining = (
                        after
                        - self.settings.up * after.dot(self.settings.up)
                    )
                    remaining = Vec3.zero()
                    break

            inward = after.dot(hit.normal)
            if inward < 0.0:
                after = after - hit.normal * inward
            remaining = after
        else:
            raise PhysicsValidationError(
                "character move iteration bound exceeded"
            )

        if remaining.length_squared() <= self.settings.minimum_move_distance**2:
            remaining = Vec3.zero()

        snap = self._ground_probe(
            world,
            position,
            ignore=ignore,
        )
        if snap is not None:
            snap_move = (
                -self.settings.up
                * self.settings.ground_snap_distance
                * snap.fraction
            )
            position = position + snap_move
            grounded = True
            ground_normal = snap.normal
            ground_body = snap.body_id
            hits.append(snap)
        elif not grounded:
            ground_normal = None
            ground_body = None

        return CharacterMoveResult(
            start_position=start,
            position=position,
            requested_displacement=displacement,
            actual_displacement=position - start,
            remaining_displacement=remaining,
            hits=tuple(hits),
            grounded=grounded,
            ground_normal=ground_normal,
            ground_body=ground_body,
            stepped=stepped,
            iterations=iterations,
        )
