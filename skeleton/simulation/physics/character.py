"""Deterministic kinematic capsule character movement.

The controller is intentionally query-driven. It reuses the rigid-body convex
TOI kernel for sweeps, but it does not inject hidden impulses or mutate scene
bodies. Character state consists only of capsule configuration, position, and
up direction; callers can therefore snapshot it alongside gameplay state.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..ecs.canonical import digest
from .body import RigidBody
from .collision import detect_collision
from .convex import convex_plane_time_of_impact, convex_time_of_impact
from .errors import PhysicsSnapshotError, PhysicsValidationError
from .math3d import EPSILON, Quat, Vec3
from .shapes import (
    BoxShape,
    CapsuleShape,
    ConvexHullShape,
    CylinderShape,
    PlaneShape,
    SphereShape,
)

_SUPPORTED_FINITE = (
    SphereShape,
    BoxShape,
    CapsuleShape,
    CylinderShape,
    ConvexHullShape,
)
_CHARACTER_STATE_DOMAIN = "skeleton.simulation.physics.character_state.v1"
_CHARACTER_STATE_VERSION = 1


def _settings_record(
    settings: "CharacterControllerSettings",
) -> dict[str, object]:
    return {
        "radius": settings.radius,
        "half_height": settings.half_height,
        "skin_width": settings.skin_width,
        "max_slope_angle": settings.max_slope_angle,
        "step_height": settings.step_height,
        "ground_probe_distance": settings.ground_probe_distance,
        "max_slide_iterations": settings.max_slide_iterations,
        "min_move_distance": settings.min_move_distance,
        "max_recovery_iterations": settings.max_recovery_iterations,
        "max_recovery_distance": settings.max_recovery_distance,
    }


def _character_state_material(
    *,
    body_id: str,
    position: Vec3,
    up: Vec3,
    settings: "CharacterControllerSettings",
) -> dict[str, object]:
    return {
        "domain": _CHARACTER_STATE_DOMAIN,
        "version": _CHARACTER_STATE_VERSION,
        "body_id": body_id,
        "position": position.to_tuple(),
        "up": up.to_tuple(),
        "settings": _settings_record(settings),
    }



def _finite_positive(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise PhysicsValidationError(f"{name} must be finite and positive")
    return value


def _finite_non_negative(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise PhysicsValidationError(
            f"{name} must be finite and non-negative"
        )
    return value


def _rotation_from_up(up: Vec3) -> Quat:
    if not isinstance(up, Vec3):
        raise PhysicsValidationError("character up must be Vec3")
    up = up.normalized()
    local_up = Vec3.axis(1)
    cosine = max(-1.0, min(1.0, local_up.dot(up)))
    if cosine >= 1.0 - 1.0e-12:
        return Quat.identity()
    if cosine <= -1.0 + 1.0e-12:
        return Quat.from_axis_angle(Vec3.axis(0), math.pi)
    axis = local_up.cross(up).normalized()
    return Quat.from_axis_angle(axis, math.acos(cosine))


@dataclass(frozen=True, slots=True)
class CharacterControllerSettings:
    radius: float = 0.4
    half_height: float = 0.6
    skin_width: float = 0.02
    max_slope_angle: float = math.radians(50.0)
    step_height: float = 0.35
    ground_probe_distance: float = 0.2
    max_slide_iterations: int = 5
    min_move_distance: float = 1.0e-6
    max_recovery_iterations: int = 8
    max_recovery_distance: float = 2.0

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
        object.__setattr__(
            self,
            "skin_width",
            _finite_non_negative(self.skin_width, name="skin_width"),
        )
        angle = _finite_non_negative(
            self.max_slope_angle,
            name="max_slope_angle",
        )
        if angle >= math.pi * 0.5:
            raise PhysicsValidationError(
                "max_slope_angle must be less than pi/2"
            )
        object.__setattr__(self, "max_slope_angle", angle)
        object.__setattr__(
            self,
            "step_height",
            _finite_non_negative(self.step_height, name="step_height"),
        )
        object.__setattr__(
            self,
            "ground_probe_distance",
            _finite_non_negative(
                self.ground_probe_distance,
                name="ground_probe_distance",
            ),
        )
        if (
            isinstance(self.max_slide_iterations, bool)
            or not isinstance(self.max_slide_iterations, int)
            or not 1 <= self.max_slide_iterations <= 32
        ):
            raise PhysicsValidationError(
                "max_slide_iterations outside supported range"
            )
        object.__setattr__(
            self,
            "min_move_distance",
            _finite_positive(
                self.min_move_distance,
                name="min_move_distance",
            ),
        )
        if (
            isinstance(self.max_recovery_iterations, bool)
            or not isinstance(self.max_recovery_iterations, int)
            or not 1 <= self.max_recovery_iterations <= 32
        ):
            raise PhysicsValidationError(
                "max_recovery_iterations outside supported range"
            )
        object.__setattr__(
            self,
            "max_recovery_distance",
            _finite_positive(
                self.max_recovery_distance,
                name="max_recovery_distance",
            ),
        )

    @property
    def slope_cosine(self) -> float:
        return math.cos(self.max_slope_angle)

    @property
    def capsule(self) -> CapsuleShape:
        return CapsuleShape(self.radius, self.half_height)


@dataclass(frozen=True, slots=True)
class CharacterControllerState:
    version: int
    body_id: str
    position: Vec3
    up: Vec3
    settings: CharacterControllerSettings
    state_digest: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version != _CHARACTER_STATE_VERSION
        ):
            raise PhysicsSnapshotError(
                "unsupported character state version"
            )
        if not isinstance(self.body_id, str) or not self.body_id:
            raise PhysicsSnapshotError(
                "character state body_id must be non-empty"
            )
        if not isinstance(self.position, Vec3) or not isinstance(self.up, Vec3):
            raise PhysicsSnapshotError(
                "character state position/up must be Vec3"
            )
        if not isinstance(self.settings, CharacterControllerSettings):
            raise PhysicsSnapshotError(
                "character state settings contract mismatch"
            )
        if abs(self.up.length() - 1.0) > 1.0e-9:
            raise PhysicsSnapshotError(
                "character state up vector must be normalized"
            )
        if (
            not isinstance(self.state_digest, str)
            or len(self.state_digest) != 64
        ):
            raise PhysicsSnapshotError(
                "character state digest must be sha256 hex"
            )
        try:
            bytes.fromhex(self.state_digest)
        except ValueError as exc:
            raise PhysicsSnapshotError(
                "character state digest is not hexadecimal"
            ) from exc


def build_character_state(
    *,
    body_id: str,
    position: Vec3,
    up: Vec3,
    settings: CharacterControllerSettings,
) -> CharacterControllerState:
    if not isinstance(body_id, str) or not body_id:
        raise PhysicsValidationError(
            "character state body_id must be non-empty"
        )
    if not isinstance(position, Vec3) or not isinstance(up, Vec3):
        raise PhysicsValidationError(
            "character state position/up must be Vec3"
        )
    if not isinstance(settings, CharacterControllerSettings):
        raise PhysicsValidationError(
            "character state settings must be CharacterControllerSettings"
        )
    normalized_up = up.normalized()
    material = _character_state_material(
        body_id=body_id,
        position=position,
        up=normalized_up,
        settings=settings,
    )
    return CharacterControllerState(
        version=_CHARACTER_STATE_VERSION,
        body_id=body_id,
        position=position,
        up=normalized_up,
        settings=settings,
        state_digest=digest(material),
    )


def verify_character_state(
    state: CharacterControllerState,
) -> CharacterControllerState:
    if not isinstance(state, CharacterControllerState):
        raise PhysicsValidationError(
            "state must be CharacterControllerState"
        )
    expected = digest(
        _character_state_material(
            body_id=state.body_id,
            position=state.position,
            up=state.up,
            settings=state.settings,
        )
    )
    if expected != state.state_digest:
        raise PhysicsSnapshotError(
            "character state digest mismatch"
        )
    return state


@dataclass(frozen=True, slots=True)
class CharacterSweepHit:
    body_id: str
    fraction: float
    distance: float
    point_character: Vec3
    point_other: Vec3
    normal: Vec3
    initial_overlap: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.body_id, str) or not self.body_id:
            raise PhysicsValidationError(
                "character sweep body_id must be non-empty"
            )
        if (
            not math.isfinite(self.fraction)
            or not 0.0 <= self.fraction <= 1.0
        ):
            raise PhysicsValidationError(
                "character sweep fraction must be in [0, 1]"
            )
        if not math.isfinite(self.distance) or self.distance < 0.0:
            raise PhysicsValidationError(
                "character sweep distance must be non-negative"
            )
        object.__setattr__(self, "normal", self.normal.normalized())
        if not isinstance(self.initial_overlap, bool):
            raise PhysicsValidationError(
                "character sweep initial_overlap must be boolean"
            )


@dataclass(frozen=True, slots=True)
class CharacterGroundState:
    grounded: bool
    body_id: str | None
    distance: float
    point: Vec3
    normal: Vec3
    slope_angle: float

    def __post_init__(self) -> None:
        if not isinstance(self.grounded, bool):
            raise PhysicsValidationError("grounded must be boolean")
        if self.body_id is not None and (
            not isinstance(self.body_id, str) or not self.body_id
        ):
            raise PhysicsValidationError(
                "ground body_id must be non-empty text or None"
            )
        if not math.isfinite(self.distance) or self.distance < 0.0:
            raise PhysicsValidationError(
                "ground distance must be non-negative"
            )
        object.__setattr__(self, "normal", self.normal.normalized())
        if (
            not math.isfinite(self.slope_angle)
            or not 0.0 <= self.slope_angle <= math.pi
        ):
            raise PhysicsValidationError("invalid ground slope angle")


@dataclass(frozen=True, slots=True)
class CharacterMoveResult:
    start_position: Vec3
    position: Vec3
    requested_displacement: Vec3
    applied_displacement: Vec3
    remaining_displacement: Vec3
    hits: tuple[CharacterSweepHit, ...]
    ground: CharacterGroundState
    iterations: int
    stepped: bool

    def __post_init__(self) -> None:
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 0
        ):
            raise PhysicsValidationError(
                "character move iterations must be non-negative integer"
            )
        if not isinstance(self.stepped, bool):
            raise PhysicsValidationError(
                "character move stepped must be boolean"
            )


@dataclass(frozen=True, slots=True)
class CharacterRecoveryResult:
    start_position: Vec3
    position: Vec3
    displacement: Vec3
    recovered: bool
    iterations: int
    body_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.recovered, bool):
            raise PhysicsValidationError("recovered must be boolean")
        if (
            isinstance(self.iterations, bool)
            or not isinstance(self.iterations, int)
            or self.iterations < 0
        ):
            raise PhysicsValidationError(
                "recovery iterations must be non-negative integer"
            )


@dataclass(frozen=True, slots=True)
class CharacterResizeResult:
    changed: bool
    old_half_height: float
    new_half_height: float
    old_position: Vec3
    position: Vec3
    blocked_by: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.changed, bool):
            raise PhysicsValidationError("resize changed must be boolean")
        for name, value in (
            ("old_half_height", self.old_half_height),
            ("new_half_height", self.new_half_height),
        ):
            if not math.isfinite(value) or value <= 0.0:
                raise PhysicsValidationError(
                    f"{name} must be finite and positive"
                )


@dataclass(frozen=True, slots=True)
class CharacterRuntimeResult:
    start_position: Vec3
    position: Vec3
    requested_velocity: Vec3
    support_velocity: Vec3
    carry_displacement: Vec3
    input_displacement: Vec3
    recovery: CharacterRecoveryResult
    move: CharacterMoveResult
    ground: CharacterGroundState

    @property
    def applied_displacement(self) -> Vec3:
        return self.position - self.start_position


class KinematicCapsuleController:
    """Stateful deterministic capsule controller backed by physics queries."""

    def __init__(
        self,
        body_id: str,
        *,
        position: Vec3 = Vec3(),
        up: Vec3 = Vec3.axis(1),
        settings: CharacterControllerSettings = CharacterControllerSettings(),
    ) -> None:
        if not isinstance(body_id, str) or not body_id:
            raise PhysicsValidationError(
                "character body_id must be non-empty text"
            )
        if not isinstance(position, Vec3):
            raise PhysicsValidationError("character position must be Vec3")
        if not isinstance(settings, CharacterControllerSettings):
            raise PhysicsValidationError(
                "settings must be CharacterControllerSettings"
            )
        self.body_id = body_id
        self.position = position
        self.up = up.normalized()
        self.settings = settings
        self.orientation = _rotation_from_up(self.up)

        # Reuse RigidBody's strict body-id validation at construction time.
        self._query_body(position, Vec3.zero(), 1.0)

    @property
    def shape(self) -> CapsuleShape:
        return self.settings.capsule

    def state_record(self) -> dict[str, object]:
        return _character_state_material(
            body_id=self.body_id,
            position=self.position,
            up=self.up,
            settings=self.settings,
        )

    @property
    def state_digest(self) -> str:
        return digest(self.state_record())

    def capture_state(self) -> CharacterControllerState:
        return build_character_state(
            body_id=self.body_id,
            position=self.position,
            up=self.up,
            settings=self.settings,
        )

    def restore_state(
        self,
        state: CharacterControllerState,
    ) -> CharacterControllerState:
        verified = verify_character_state(state)
        if verified.body_id != self.body_id:
            raise PhysicsSnapshotError(
                "character state body identity mismatch"
            )

        new_up = verified.up.normalized()
        new_orientation = _rotation_from_up(new_up)
        # All validation and derived-state construction happens before mutation.
        self.position = verified.position
        self.up = new_up
        self.orientation = new_orientation
        self.settings = verified.settings
        return verified

    def _query_body_with_shape(
        self,
        position: Vec3,
        shape: CapsuleShape,
        *,
        displacement: Vec3 = Vec3.zero(),
        dt: float = 1.0,
    ) -> RigidBody:
        if not isinstance(position, Vec3) or not isinstance(shape, CapsuleShape):
            raise PhysicsValidationError(
                "character query body requires Vec3 position and CapsuleShape"
            )
        dt = _finite_positive(dt, name="dt")
        return RigidBody.kinematic(
            self.body_id,
            shape,
            position=position,
            orientation=self.orientation,
            linear_velocity=displacement / dt,
        )

    @staticmethod
    def _validate_bodies(bodies: tuple[RigidBody, ...]) -> None:
        if not isinstance(bodies, tuple) or not all(
            isinstance(body, RigidBody) for body in bodies
        ):
            raise PhysicsValidationError(
                "character bodies must be tuple[RigidBody, ...]"
            )

    def _overlaps_for_shape(
        self,
        position: Vec3,
        shape: CapsuleShape,
        bodies: tuple[RigidBody, ...],
        *,
        ignore: tuple[str, ...] = (),
    ) -> tuple[tuple[RigidBody, float, Vec3], ...]:
        self._validate_bodies(bodies)
        ignored = set(ignore)
        ignored.add(self.body_id)
        query = self._query_body_with_shape(position, shape)
        overlaps: list[tuple[RigidBody, float, Vec3]] = []
        for target in sorted(bodies, key=lambda row: row.body_id):
            if target.body_id in ignored:
                continue
            manifold = detect_collision(query, target)
            if manifold is None or manifold.penetration <= EPSILON:
                continue
            overlaps.append(
                (target, manifold.penetration, manifold.normal)
            )
        return tuple(
            sorted(
                overlaps,
                key=lambda row: (-row[1], row[0].body_id),
            )
        )

    def _query_body(
        self,
        position: Vec3,
        displacement: Vec3,
        dt: float,
    ) -> RigidBody:
        if not isinstance(position, Vec3) or not isinstance(displacement, Vec3):
            raise PhysicsValidationError(
                "character query position/displacement must be Vec3"
            )
        dt = _finite_positive(dt, name="dt")
        return self._query_body_with_shape(
            position,
            self.shape,
            displacement=displacement,
            dt=dt,
        )

    def is_walkable(self, normal: Vec3) -> bool:
        if not isinstance(normal, Vec3):
            raise PhysicsValidationError("walkable normal must be Vec3")
        return normal.normalized().dot(self.up) >= self.settings.slope_cosine

    def _sweep_hits(
        self,
        position: Vec3,
        displacement: Vec3,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        ignore: tuple[str, ...],
    ) -> tuple[CharacterSweepHit, ...]:
        dt = _finite_positive(dt, name="dt")
        if not isinstance(displacement, Vec3):
            raise PhysicsValidationError(
                "character displacement must be Vec3"
            )
        if not isinstance(bodies, tuple) or not all(
            isinstance(body, RigidBody) for body in bodies
        ):
            raise PhysicsValidationError(
                "character sweep bodies must be tuple[RigidBody, ...]"
            )

        ignored = set(ignore)
        ignored.add(self.body_id)
        moving = self._query_body(position, displacement, dt)
        path_length = displacement.length()
        hits: list[CharacterSweepHit] = []

        for target in sorted(bodies, key=lambda row: row.body_id):
            if target.body_id in ignored:
                continue

            if isinstance(target.shape, PlaneShape):
                toi = convex_plane_time_of_impact(
                    moving,
                    target,
                    dt,
                    max_iterations=64,
                    distance_tolerance=1.0e-7,
                    time_tolerance=1.0e-9,
                )
            elif isinstance(target.shape, _SUPPORTED_FINITE):
                toi = convex_time_of_impact(
                    moving,
                    target,
                    dt,
                    max_iterations=64,
                    distance_iterations=64,
                    distance_tolerance=1.0e-7,
                    time_tolerance=1.0e-9,
                )
            else:
                continue

            if toi is None:
                continue

            if toi.time <= EPSILON:
                relative_velocity = (
                    target.velocity_at_world_point(toi.point_b)
                    - moving.velocity_at_world_point(toi.point_a)
                )
                if relative_velocity.dot(toi.normal) >= -EPSILON:
                    continue

            hits.append(
                CharacterSweepHit(
                    body_id=target.body_id,
                    fraction=toi.fraction,
                    distance=path_length * toi.fraction,
                    point_character=toi.point_a,
                    point_other=toi.point_b,
                    # TOI normal is character A -> obstacle B. Gameplay
                    # response needs the obstacle surface normal pointing back
                    # toward the character.
                    normal=-toi.normal,
                    initial_overlap=toi.initial_overlap,
                )
            )

        return tuple(
            sorted(
                hits,
                key=lambda row: (
                    row.fraction,
                    row.body_id,
                ),
            )
        )

    def sweep(
        self,
        displacement: Vec3,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        position: Vec3 | None = None,
        ignore: tuple[str, ...] = (),
    ) -> CharacterSweepHit | None:
        origin = self.position if position is None else position
        hits = self._sweep_hits(
            origin,
            displacement,
            bodies,
            dt=dt,
            ignore=ignore,
        )
        return hits[0] if hits else None

    def ground_probe(
        self,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        position: Vec3 | None = None,
        ignore: tuple[str, ...] = (),
        distance: float | None = None,
    ) -> CharacterGroundState:
        origin = self.position if position is None else position
        probe_distance = (
            self.settings.ground_probe_distance
            if distance is None
            else _finite_non_negative(distance, name="ground probe distance")
        )
        if probe_distance <= 0.0:
            return CharacterGroundState(
                False,
                None,
                0.0,
                origin,
                self.up,
                0.0,
            )

        displacement = -self.up * probe_distance
        hits = self._sweep_hits(
            origin,
            displacement,
            bodies,
            dt=dt,
            ignore=ignore,
        )
        for hit in hits:
            alignment = max(-1.0, min(1.0, hit.normal.dot(self.up)))
            slope = math.acos(alignment)
            if alignment >= self.settings.slope_cosine:
                return CharacterGroundState(
                    True,
                    hit.body_id,
                    hit.distance,
                    hit.point_other,
                    hit.normal,
                    slope,
                )

        return CharacterGroundState(
            False,
            None,
            probe_distance,
            origin + displacement,
            self.up,
            0.0,
        )

    @staticmethod
    def _slide(displacement: Vec3, normal: Vec3) -> Vec3:
        into_surface = displacement.dot(normal)
        if into_surface >= 0.0:
            return displacement
        return displacement - normal * into_surface

    def _try_step(
        self,
        position: Vec3,
        remaining: Vec3,
        obstacle: CharacterSweepHit,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        ignore: tuple[str, ...],
    ) -> tuple[Vec3, Vec3, CharacterSweepHit] | None:
        step_height = self.settings.step_height
        if step_height <= 0.0 or self.is_walkable(obstacle.normal):
            return None

        vertical_amount = remaining.dot(self.up)
        horizontal = remaining - self.up * vertical_amount
        if horizontal.length() <= self.settings.min_move_distance:
            return None

        up_move = self.up * step_height
        up_hit = self.sweep(
            up_move,
            bodies,
            dt=dt,
            position=position,
            ignore=ignore,
        )
        if up_hit is not None and (
            up_hit.distance < step_height - self.settings.skin_width
        ):
            return None

        raised = position + up_move
        forward_hit = self.sweep(
            horizontal,
            bodies,
            dt=dt,
            position=raised,
            ignore=ignore,
        )
        if forward_hit is not None:
            return None

        forward = raised + horizontal
        down_distance = (
            step_height
            + self.settings.ground_probe_distance
            + self.settings.skin_width
        )
        down_hits = self._sweep_hits(
            forward,
            -self.up * down_distance,
            bodies,
            dt=dt,
            ignore=ignore,
        )
        landing = next(
            (hit for hit in down_hits if self.is_walkable(hit.normal)),
            None,
        )
        if landing is None:
            return None

        descend = max(0.0, landing.distance - self.settings.skin_width)
        final_position = forward - self.up * descend

        # A successful step consumes downward requested motion because the
        # character has acquired a valid supporting surface. Positive upward
        # intent remains available for a jump or ledge climb.
        residual_vertical = self.up * max(0.0, vertical_amount)
        return final_position, residual_vertical, landing

    def recover_overlaps(
        self,
        bodies: tuple[RigidBody, ...],
        *,
        ignore: tuple[str, ...] = (),
    ) -> CharacterRecoveryResult:
        self._validate_bodies(bodies)
        start = self.position
        position = start
        touched: list[str] = []
        total = Vec3.zero()
        iterations = 0

        for iteration in range(1, self.settings.max_recovery_iterations + 1):
            overlaps = self._overlaps_for_shape(
                position,
                self.shape,
                bodies,
                ignore=ignore,
            )
            if not overlaps:
                break

            iterations = iteration
            target, penetration, normal = overlaps[0]
            push_distance = penetration + self.settings.skin_width
            push = -normal * push_distance
            if total.length() + push.length() > self.settings.max_recovery_distance:
                raise PhysicsValidationError(
                    "character overlap recovery distance bound exceeded"
                )
            position = position + push
            total = position - start
            touched.append(target.body_id)

        remaining = self._overlaps_for_shape(
            position,
            self.shape,
            bodies,
            ignore=ignore,
        )
        if remaining:
            raise PhysicsValidationError(
                "character overlap recovery iteration bound exceeded"
            )

        self.position = position
        return CharacterRecoveryResult(
            start_position=start,
            position=position,
            displacement=position - start,
            recovered=(position - start).length_squared() > EPSILON * EPSILON,
            iterations=iterations,
            body_ids=tuple(touched),
        )

    def can_resize(
        self,
        new_half_height: float,
        bodies: tuple[RigidBody, ...],
        *,
        ignore: tuple[str, ...] = (),
        preserve_foot: bool = True,
    ) -> CharacterResizeResult:
        new_half_height = _finite_positive(
            new_half_height,
            name="new_half_height",
        )
        if not isinstance(preserve_foot, bool):
            raise PhysicsValidationError("preserve_foot must be boolean")
        old_half_height = self.settings.half_height
        delta = new_half_height - old_half_height
        candidate_position = (
            self.position + self.up * delta
            if preserve_foot
            else self.position
        )
        candidate_shape = CapsuleShape(
            self.settings.radius,
            new_half_height,
        )
        overlaps = self._overlaps_for_shape(
            candidate_position,
            candidate_shape,
            bodies,
            ignore=ignore,
        )
        return CharacterResizeResult(
            changed=not overlaps and abs(delta) > EPSILON,
            old_half_height=old_half_height,
            new_half_height=new_half_height,
            old_position=self.position,
            position=candidate_position if not overlaps else self.position,
            blocked_by=tuple(row[0].body_id for row in overlaps),
        )

    def resize(
        self,
        new_half_height: float,
        bodies: tuple[RigidBody, ...],
        *,
        ignore: tuple[str, ...] = (),
        preserve_foot: bool = True,
    ) -> CharacterResizeResult:
        result = self.can_resize(
            new_half_height,
            bodies,
            ignore=ignore,
            preserve_foot=preserve_foot,
        )
        if result.blocked_by:
            return result
        self.position = result.position
        self.settings = replace(
            self.settings,
            half_height=result.new_half_height,
        )
        return result

    def support_velocity(
        self,
        ground: CharacterGroundState,
        bodies: tuple[RigidBody, ...],
    ) -> Vec3:
        self._validate_bodies(bodies)
        if not ground.grounded or ground.body_id is None:
            return Vec3.zero()
        for body in bodies:
            if body.body_id == ground.body_id:
                return body.velocity_at_world_point(ground.point)
        return Vec3.zero()

    def runtime_step(
        self,
        requested_velocity: Vec3,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        ignore: tuple[str, ...] = (),
        recover_overlaps: bool = True,
        carry_support: bool = True,
    ) -> CharacterRuntimeResult:
        if not isinstance(requested_velocity, Vec3):
            raise PhysicsValidationError(
                "requested_velocity must be Vec3"
            )
        if not isinstance(recover_overlaps, bool) or not isinstance(
            carry_support,
            bool,
        ):
            raise PhysicsValidationError(
                "runtime flags must be boolean"
            )
        dt = _finite_positive(dt, name="dt")
        self._validate_bodies(bodies)
        checkpoint = self.capture_state()
        start = self.position

        try:
            if recover_overlaps:
                recovery = self.recover_overlaps(
                    bodies,
                    ignore=ignore,
                )
            else:
                recovery = CharacterRecoveryResult(
                    start_position=self.position,
                    position=self.position,
                    displacement=Vec3.zero(),
                    recovered=False,
                    iterations=0,
                    body_ids=(),
                )

            pre_ground = self.ground_probe(
                bodies,
                dt=dt,
                ignore=ignore,
            )
            support_velocity = (
                self.support_velocity(pre_ground, bodies)
                if carry_support
                else Vec3.zero()
            )
            carry = support_velocity * dt
            input_displacement = requested_velocity * dt
            move = self.move(
                carry + input_displacement,
                bodies,
                dt=dt,
                ignore=ignore,
            )
            return CharacterRuntimeResult(
                start_position=start,
                position=self.position,
                requested_velocity=requested_velocity,
                support_velocity=support_velocity,
                carry_displacement=carry,
                input_displacement=input_displacement,
                recovery=recovery,
                move=move,
                ground=move.ground,
            )
        except Exception:
            self.restore_state(checkpoint)
            raise

    def move(
        self,
        displacement: Vec3,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        ignore: tuple[str, ...] = (),
    ) -> CharacterMoveResult:
        if not isinstance(displacement, Vec3):
            raise PhysicsValidationError(
                "character displacement must be Vec3"
            )
        dt = _finite_positive(dt, name="dt")
        start = self.position
        position = start
        remaining = displacement
        hits: list[CharacterSweepHit] = []
        stepped = False
        iterations = 0

        for iteration in range(1, self.settings.max_slide_iterations + 1):
            iterations = iteration
            remaining_length = remaining.length()
            if remaining_length <= self.settings.min_move_distance:
                remaining = Vec3.zero()
                break

            hit = self.sweep(
                remaining,
                bodies,
                dt=dt,
                position=position,
                ignore=ignore,
            )
            if hit is None:
                position = position + remaining
                remaining = Vec3.zero()
                break

            hits.append(hit)
            direction = remaining / remaining_length
            safe_distance = max(
                0.0,
                hit.distance - self.settings.skin_width,
            )
            safe_move = direction * min(remaining_length, safe_distance)
            position = position + safe_move
            unconsumed = remaining - safe_move

            step = self._try_step(
                position,
                unconsumed,
                hit,
                bodies,
                dt=dt,
                ignore=ignore,
            )
            if step is not None:
                position, remaining, landing = step
                hits.append(landing)
                stepped = True
                continue

            slid = self._slide(unconsumed, hit.normal)
            if (
                safe_move.length() <= self.settings.min_move_distance
                and (slid - remaining).length()
                <= self.settings.min_move_distance
            ):
                remaining = Vec3.zero()
                break
            remaining = slid

        self.position = position
        ground = self.ground_probe(
            bodies,
            dt=dt,
            position=position,
            ignore=ignore,
        )
        return CharacterMoveResult(
            start_position=start,
            position=position,
            requested_displacement=displacement,
            applied_displacement=position - start,
            remaining_displacement=remaining,
            hits=tuple(hits),
            ground=ground,
            iterations=iterations,
            stepped=stepped,
        )
