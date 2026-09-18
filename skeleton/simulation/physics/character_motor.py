"""Deterministic locomotion motor layered over the capsule controller."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import RigidBody
from .character import (
    CharacterGroundState,
    CharacterMoveResult,
    KinematicCapsuleController,
)
from .errors import PhysicsValidationError
from .math3d import Vec3


def _positive(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value <= 0.0:
        raise PhysicsValidationError(f"{name} must be finite and positive")
    return value


def _non_negative(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise PhysicsValidationError(
            f"{name} must be finite and non-negative"
        )
    return value


@dataclass(frozen=True, slots=True)
class CharacterMotorSettings:
    max_speed: float = 7.0
    ground_acceleration: float = 45.0
    air_acceleration: float = 12.0
    gravity: float = 24.0
    jump_speed: float = 8.0
    terminal_fall_speed: float = 45.0
    ground_snap_distance: float = 0.3
    support_velocity_inheritance: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "max_speed",
            "ground_acceleration",
            "air_acceleration",
            "gravity",
            "jump_speed",
            "terminal_fall_speed",
        ):
            object.__setattr__(
                self,
                name,
                _positive(getattr(self, name), name=name),
            )
        object.__setattr__(
            self,
            "ground_snap_distance",
            _non_negative(
                self.ground_snap_distance,
                name="ground_snap_distance",
            ),
        )
        inheritance = _non_negative(
            self.support_velocity_inheritance,
            name="support_velocity_inheritance",
        )
        if inheritance > 1.0:
            raise PhysicsValidationError(
                "support_velocity_inheritance must be in [0, 1]"
            )
        object.__setattr__(
            self,
            "support_velocity_inheritance",
            inheritance,
        )


@dataclass(frozen=True, slots=True)
class CharacterMotorResult:
    move: CharacterMoveResult
    ground_before: CharacterGroundState
    ground_after: CharacterGroundState
    velocity_before: Vec3
    velocity: Vec3
    desired_velocity: Vec3
    support_velocity: Vec3
    jumped: bool
    snapped_distance: float

    def __post_init__(self) -> None:
        if not isinstance(self.jumped, bool):
            raise PhysicsValidationError("motor jumped must be boolean")
        if (
            not math.isfinite(self.snapped_distance)
            or self.snapped_distance < 0.0
        ):
            raise PhysicsValidationError(
                "snapped_distance must be finite and non-negative"
            )


class KinematicCharacterMotor:
    """Velocity/acceleration policy for KinematicCapsuleController."""

    def __init__(
        self,
        *,
        velocity: Vec3 = Vec3.zero(),
        settings: CharacterMotorSettings = CharacterMotorSettings(),
    ) -> None:
        if not isinstance(velocity, Vec3):
            raise PhysicsValidationError("motor velocity must be Vec3")
        if not isinstance(settings, CharacterMotorSettings):
            raise PhysicsValidationError(
                "settings must be CharacterMotorSettings"
            )
        self.velocity = velocity
        self.settings = settings
        self.grounded = False
        self.support_body_id: str | None = None
        self.support_velocity = Vec3.zero()

    @staticmethod
    def _move_towards(
        current: Vec3,
        target: Vec3,
        max_delta: float,
    ) -> Vec3:
        delta = target - current
        distance = delta.length()
        if distance <= max_delta or distance <= 1.0e-12:
            return target
        return current + delta * (max_delta / distance)

    @staticmethod
    def _clip_velocity(velocity: Vec3, normal: Vec3) -> Vec3:
        inward = velocity.dot(normal)
        if inward >= 0.0:
            return velocity
        return velocity - normal * inward

    @staticmethod
    def _body_map(
        bodies: tuple[RigidBody, ...],
    ) -> dict[str, RigidBody]:
        if not isinstance(bodies, tuple) or not all(
            isinstance(body, RigidBody) for body in bodies
        ):
            raise PhysicsValidationError(
                "motor bodies must be tuple[RigidBody, ...]"
            )
        return {body.body_id: body for body in bodies}

    def _support_velocity(
        self,
        ground: CharacterGroundState,
        bodies: dict[str, RigidBody],
    ) -> Vec3:
        if not ground.grounded or ground.body_id is None:
            return Vec3.zero()
        body = bodies.get(ground.body_id)
        if body is None:
            return Vec3.zero()
        velocity = body.velocity_at_world_point(ground.point)
        return velocity * self.settings.support_velocity_inheritance

    def _desired_tangent(
        self,
        desired_velocity: Vec3,
        up: Vec3,
        ground: CharacterGroundState,
    ) -> Vec3:
        tangent = desired_velocity - up * desired_velocity.dot(up)
        speed = tangent.length()
        if speed > self.settings.max_speed:
            tangent = tangent * (self.settings.max_speed / speed)
        if ground.grounded:
            into_ground = tangent.dot(ground.normal)
            tangent = tangent - ground.normal * into_ground
            # Projection onto an inclined plane changes magnitude. Clamp again
            # rather than renormalizing so requested input never gains energy.
            speed = tangent.length()
            if speed > self.settings.max_speed:
                tangent = tangent * (self.settings.max_speed / speed)
        return tangent

    def _snap_to_ground(
        self,
        controller: KinematicCapsuleController,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        ignore: tuple[str, ...],
    ) -> tuple[CharacterGroundState, float]:
        if self.settings.ground_snap_distance <= 0.0:
            return (
                controller.ground_probe(
                    bodies,
                    dt=dt,
                    ignore=ignore,
                ),
                0.0,
            )

        ground = controller.ground_probe(
            bodies,
            dt=dt,
            ignore=ignore,
            distance=self.settings.ground_snap_distance,
        )
        if not ground.grounded:
            return ground, 0.0

        snap = max(
            0.0,
            ground.distance - controller.settings.skin_width,
        )
        if snap <= controller.settings.min_move_distance:
            return ground, 0.0

        controller.position = controller.position - controller.up * snap
        settled = controller.ground_probe(
            bodies,
            dt=dt,
            ignore=ignore,
            distance=max(
                controller.settings.ground_probe_distance,
                controller.settings.skin_width * 2.0,
            ),
        )
        return settled, snap

    @staticmethod
    def _replace_move_position(
        move: CharacterMoveResult,
        position: Vec3,
        ground: CharacterGroundState,
    ) -> CharacterMoveResult:
        return CharacterMoveResult(
            start_position=move.start_position,
            position=position,
            requested_displacement=move.requested_displacement,
            applied_displacement=position - move.start_position,
            remaining_displacement=move.remaining_displacement,
            hits=move.hits,
            ground=ground,
            iterations=move.iterations,
            stepped=move.stepped,
        )

    def step(
        self,
        controller: KinematicCapsuleController,
        desired_velocity: Vec3,
        bodies: tuple[RigidBody, ...],
        *,
        dt: float,
        jump: bool = False,
        ignore: tuple[str, ...] = (),
    ) -> CharacterMotorResult:
        if not isinstance(controller, KinematicCapsuleController):
            raise PhysicsValidationError(
                "controller must be KinematicCapsuleController"
            )
        if not isinstance(desired_velocity, Vec3):
            raise PhysicsValidationError(
                "desired_velocity must be Vec3"
            )
        if not isinstance(jump, bool):
            raise PhysicsValidationError("jump must be boolean")
        dt = _positive(dt, name="dt")
        body_map = self._body_map(bodies)
        up = controller.up
        velocity_before = self.velocity

        ground_before = controller.ground_probe(
            bodies,
            dt=dt,
            ignore=ignore,
            distance=max(
                self.settings.ground_snap_distance,
                controller.settings.ground_probe_distance,
            ),
        )
        current_support = self._support_velocity(
            ground_before,
            body_map,
        )

        if ground_before.grounded and self.grounded:
            relative_velocity = self.velocity - self.support_velocity
        else:
            relative_velocity = self.velocity

        desired_tangent = self._desired_tangent(
            desired_velocity,
            up,
            ground_before,
        )
        vertical_speed = relative_velocity.dot(up)
        tangent_velocity = (
            relative_velocity - up * vertical_speed
        )

        jumped = bool(jump and ground_before.grounded)
        if ground_before.grounded:
            tangent_velocity = self._move_towards(
                tangent_velocity,
                desired_tangent,
                self.settings.ground_acceleration * dt,
            )
            if jumped:
                relative_velocity = (
                    tangent_velocity + up * self.settings.jump_speed
                )
                velocity = current_support + relative_velocity
            else:
                # Supported motion should not accumulate gravity into the
                # ground. The controller's slope/step queries own positional
                # support while the motor retains only tangential intent.
                relative_velocity = tangent_velocity
                velocity = current_support + relative_velocity
        else:
            tangent_velocity = self._move_towards(
                tangent_velocity,
                desired_tangent,
                self.settings.air_acceleration * dt,
            )
            vertical_speed = max(
                -self.settings.terminal_fall_speed,
                vertical_speed - self.settings.gravity * dt,
            )
            velocity = tangent_velocity + up * vertical_speed

        displacement = velocity * dt
        move = controller.move(
            displacement,
            bodies,
            dt=dt,
            ignore=ignore,
        )

        clipped = velocity
        for hit in move.hits:
            clipped = self._clip_velocity(clipped, hit.normal)

        ground_after = move.ground
        snapped_distance = 0.0
        if (
            not jumped
            and clipped.dot(up) <= 0.0
        ):
            ground_after, snapped_distance = self._snap_to_ground(
                controller,
                bodies,
                dt=dt,
                ignore=ignore,
            )
            if snapped_distance > 0.0:
                move = self._replace_move_position(
                    move,
                    controller.position,
                    ground_after,
                )

        support_after = self._support_velocity(
            ground_after,
            body_map,
        )
        if ground_after.grounded and not jumped:
            clipped = self._clip_velocity(
                clipped,
                ground_after.normal,
            )

        self.velocity = clipped
        self.grounded = ground_after.grounded and not jumped
        self.support_body_id = (
            ground_after.body_id if self.grounded else None
        )
        self.support_velocity = (
            support_after if self.grounded else Vec3.zero()
        )

        return CharacterMotorResult(
            move=move,
            ground_before=ground_before,
            ground_after=ground_after,
            velocity_before=velocity_before,
            velocity=self.velocity,
            desired_velocity=desired_velocity,
            support_velocity=self.support_velocity,
            jumped=jumped,
            snapped_distance=snapped_distance,
        )
