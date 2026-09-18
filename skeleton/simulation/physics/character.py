"""Deterministic kinematic capsule character motion built on physics queries.

The controller does not invent a second collision model. Finite targets use the
same support-mapped conservative advancement as rigid-body CCD, while static
planes use exact capsule support distance. Motion is bounded by slide iterations,
slope classification, skin width, ground probing, and one deterministic step-up
attempt per blocking contact.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import BodyType, RigidBody
from .convex import convex_time_of_impact
from .errors import PhysicsValidationError
from .math3d import EPSILON, Quat, Transform, Vec3
from .shapes import CapsuleShape, PlaneShape


def _finite_non_negative(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise PhysicsValidationError(
            f"{name} must be finite and non-negative"
        )
    return value


def _positive(value: float, *, name: str) -> float:
    value = _finite_non_negative(value, name=name)
    if value <= 0.0:
        raise PhysicsValidationError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class CharacterControllerSettings:
    radius: float = 0.4
    half_height: float = 0.8
    skin_width: float = 0.02
    max_slope_degrees: float = 50.0
    step_height: float = 0.35
    ground_probe_distance: float = 0.12
    max_slides: int = 6
    min_move_distance: float = 1.0e-5
    snap_to_ground: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _positive(self.radius, name="radius"))
        object.__setattr__(
            self,
            "half_height",
            _positive(self.half_height, name="half_height"),
        )
        object.__setattr__(
            self,
            "skin_width",
            _finite_non_negative(self.skin_width, name="skin_width"),
        )
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
        object.__setattr__(
            self,
            "min_move_distance",
            _positive(self.min_move_distance, name="min_move_distance"),
        )
        if (
            isinstance(self.max_slope_degrees, bool)
            or not isinstance(self.max_slope_degrees, (int, float))
            or not math.isfinite(float(self.max_slope_degrees))
            or not 0.0 <= float(self.max_slope_degrees) < 90.0
        ):
            raise PhysicsValidationError(
                "max_slope_degrees must be in [0, 90)"
            )
        object.__setattr__(
            self,
            "max_slope_degrees",
            float(self.max_slope_degrees),
        )
        if (
            isinstance(self.max_slides, bool)
            or not isinstance(self.max_slides, int)
            or not 1 <= self.max_slides <= 32
        ):
            raise PhysicsValidationError(
                "max_slides outside supported range"
            )
        if not isinstance(self.snap_to_ground, bool):
            raise PhysicsValidationError(
                "snap_to_ground must be boolean"
            )

    @property
    def walkable_dot(self) -> float:
        return math.cos(math.radians(self.max_slope_degrees))


@dataclass(frozen=True, slots=True)
class CharacterSweepHit:
    body_id: str
    fraction: float
    distance: float
    point: Vec3
    normal: Vec3
    walkable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.body_id, str) or not self.body_id:
            raise PhysicsValidationError(
                "character hit body_id must be non-empty"
            )
        if (
            not math.isfinite(self.fraction)
            or not 0.0 <= self.fraction <= 1.0
        ):
            raise PhysicsValidationError(
                "character hit fraction must be in [0, 1]"
            )
        if not math.isfinite(self.distance) or self.distance < 0.0:
            raise PhysicsValidationError(
                "character hit distance must be non-negative"
            )
        if not isinstance(self.point, Vec3):
            raise PhysicsValidationError("character hit point must be Vec3")
        object.__setattr__(self, "normal", self.normal.normalized())
        if not isinstance(self.walkable, bool):
            raise PhysicsValidationError(
                "character hit walkable must be boolean"
            )


@dataclass(frozen=True, slots=True)
class CharacterMoveResult:
    start_position: Vec3
    position: Vec3
    requested_displacement: Vec3
    applied_displacement: Vec3
    remaining_displacement: Vec3
    grounded: bool
    ground_normal: Vec3 | None
    hits: tuple[CharacterSweepHit, ...]
    slide_iterations: int
    stepped: bool

    def __post_init__(self) -> None:
        for name in (
            "start_position",
            "position",
            "requested_displacement",
            "applied_displacement",
            "remaining_displacement",
        ):
            if not isinstance(getattr(self, name), Vec3):
                raise PhysicsValidationError(
                    f"character result {name} must be Vec3"
                )
        if not isinstance(self.grounded, bool):
            raise PhysicsValidationError(
                "character result grounded must be boolean"
            )
        if self.ground_normal is not None:
            object.__setattr__(
                self,
                "ground_normal",
                self.ground_normal.normalized(),
            )
        if (
            isinstance(self.slide_iterations, bool)
            or not isinstance(self.slide_iterations, int)
            or self.slide_iterations < 0
        ):
            raise PhysicsValidationError(
                "character slide_iterations must be non-negative integer"
            )
        if not isinstance(self.stepped, bool):
            raise PhysicsValidationError(
                "character result stepped must be boolean"
            )


class KinematicCapsuleController:
    """Bounded deterministic capsule slide/ground/step controller."""

    _QUERY_BODY_ID = "character.query"

    def __init__(
        self,
        *,
        position: Vec3,
        orientation: Quat = Quat.identity(),
        settings: CharacterControllerSettings = CharacterControllerSettings(),
    ) -> None:
        if not isinstance(position, Vec3):
            raise PhysicsValidationError(
                "character position must be Vec3"
            )
        if not isinstance(orientation, Quat):
            raise PhysicsValidationError(
                "character orientation must be Quat"
            )
        if not isinstance(settings, CharacterControllerSettings):
            raise PhysicsValidationError(
                "settings must be CharacterControllerSettings"
            )
        self.position = position
        self.orientation = orientation.normalized()
        self.settings = settings

    @property
    def up(self) -> Vec3:
        return self.orientation.rotate(Vec3.axis(1)).normalized()

    @property
    def shape(self) -> CapsuleShape:
        return CapsuleShape(
            self.settings.radius,
            self.settings.half_height,
        )

    def _query_shape(self) -> CapsuleShape:
        return CapsuleShape(
            self.settings.radius + self.settings.skin_width,
            self.settings.half_height,
        )

    def _walkable(self, normal: Vec3) -> bool:
        return normal.normalized().dot(self.up) >= self.settings.walkable_dot

    @staticmethod
    def _ordered_bodies(
        bodies: tuple[RigidBody, ...] | list[RigidBody],
    ) -> tuple[RigidBody, ...]:
        try:
            rows = tuple(bodies)
        except TypeError as exc:
            raise PhysicsValidationError(
                "character bodies must be iterable"
            ) from exc
        if not all(isinstance(row, RigidBody) for row in rows):
            raise PhysicsValidationError(
                "character bodies must contain RigidBody values"
            )
        ids = [row.body_id for row in rows]
        if len(ids) != len(set(ids)):
            raise PhysicsValidationError(
                "character bodies must have unique ids"
            )
        return tuple(sorted(rows, key=lambda row: row.body_id))

    def _query_body(
        self,
        position: Vec3,
        displacement: Vec3,
    ) -> RigidBody:
        return RigidBody.kinematic(
            self._QUERY_BODY_ID,
            self._query_shape(),
            position=position,
            orientation=self.orientation,
            linear_velocity=displacement,
        )

    def _plane_sweep(
        self,
        position: Vec3,
        displacement: Vec3,
        plane: RigidBody,
    ) -> CharacterSweepHit | None:
        if not isinstance(plane.shape, PlaneShape):
            raise PhysicsValidationError(
                "plane sweep target must be PlaneShape"
            )
        if plane.body_type is not BodyType.STATIC:
            return None

        query_shape = self._query_shape()
        transform = Transform(position, self.orientation)
        normal, offset = plane.shape.world_equation(plane.transform)
        deepest = query_shape.support(-normal, transform)
        signed_distance = normal.dot(deepest) - offset
        velocity = displacement.dot(normal)

        if signed_distance <= EPSILON:
            if velocity >= -EPSILON:
                return None
            fraction = 0.0
        else:
            if velocity >= -EPSILON:
                return None
            fraction = signed_distance / -velocity
            if fraction < 0.0 or fraction > 1.0:
                return None

        point = deepest + displacement * fraction
        return CharacterSweepHit(
            body_id=plane.body_id,
            fraction=min(1.0, max(0.0, fraction)),
            distance=displacement.length() * min(
                1.0,
                max(0.0, fraction),
            ),
            point=point,
            normal=normal,
            walkable=self._walkable(normal),
        )

    def _finite_sweep(
        self,
        position: Vec3,
        displacement: Vec3,
        target: RigidBody,
    ) -> CharacterSweepHit | None:
        if target.body_id == self._QUERY_BODY_ID:
            raise PhysicsValidationError(
                "world body id collides with reserved character query id"
            )
        query = self._query_body(position, displacement)
        hit = convex_time_of_impact(
            query,
            target,
            1.0,
            max_iterations=64,
            distance_iterations=64,
            distance_tolerance=max(
                1.0e-7,
                self.settings.skin_width * 1.0e-4,
            ),
            time_tolerance=1.0e-9,
        )
        if hit is None:
            return None

        normal = -hit.normal
        if hit.time <= EPSILON and displacement.dot(normal) >= -EPSILON:
            return None

        fraction = min(1.0, max(0.0, hit.fraction))
        return CharacterSweepHit(
            body_id=target.body_id,
            fraction=fraction,
            distance=displacement.length() * fraction,
            point=hit.point_a,
            normal=normal,
            walkable=self._walkable(normal),
        )

    def _sweep_from(
        self,
        position: Vec3,
        displacement: Vec3,
        bodies: tuple[RigidBody, ...],
    ) -> CharacterSweepHit | None:
        if displacement.length() <= self.settings.min_move_distance:
            return None

        hits: list[CharacterSweepHit] = []
        for body in bodies:
            if isinstance(body.shape, PlaneShape):
                hit = self._plane_sweep(position, displacement, body)
            else:
                hit = self._finite_sweep(position, displacement, body)
            if hit is not None:
                hits.append(hit)

        if not hits:
            return None
        return min(
            hits,
            key=lambda row: (
                row.fraction,
                row.body_id,
            ),
        )

    def sweep(
        self,
        displacement: Vec3,
        bodies: tuple[RigidBody, ...] | list[RigidBody],
    ) -> CharacterSweepHit | None:
        if not isinstance(displacement, Vec3):
            raise PhysicsValidationError(
                "character displacement must be Vec3"
            )
        return self._sweep_from(
            self.position,
            displacement,
            self._ordered_bodies(bodies),
        )

    def _try_step(
        self,
        displacement: Vec3,
        bodies: tuple[RigidBody, ...],
    ) -> tuple[Vec3, tuple[CharacterSweepHit, ...]] | None:
        if self.settings.step_height <= 0.0:
            return None

        up = self.up
        vertical = displacement.dot(up)
        horizontal = displacement - up * vertical
        if horizontal.length() <= self.settings.min_move_distance:
            return None
        if abs(vertical) > self.settings.step_height:
            return None

        original = self.position
        rise = up * self.settings.step_height
        ceiling = self._sweep_from(original, rise, bodies)
        if ceiling is not None and ceiling.fraction < 1.0 - 1.0e-9:
            return None

        raised = original + rise
        blocker = self._sweep_from(raised, horizontal, bodies)
        if blocker is not None:
            return None

        advanced = raised + horizontal
        down_distance = (
            self.settings.step_height
            + self.settings.ground_probe_distance
        )
        down = -up * down_distance
        landing = self._sweep_from(advanced, down, bodies)
        if landing is None or not landing.walkable:
            return None

        final = advanced + down * landing.fraction
        rise_amount = (final - original).dot(up)
        if rise_amount > self.settings.step_height + 1.0e-7:
            return None
        if rise_amount < -self.settings.ground_probe_distance - 1.0e-7:
            return None
        return final, (landing,)

    def probe_ground(
        self,
        bodies: tuple[RigidBody, ...] | list[RigidBody],
        *,
        distance: float | None = None,
    ) -> CharacterSweepHit | None:
        ordered = self._ordered_bodies(bodies)
        probe_distance = (
            self.settings.ground_probe_distance
            if distance is None
            else _finite_non_negative(distance, name="distance")
        )
        if probe_distance <= 0.0:
            return None
        hit = self._sweep_from(
            self.position,
            -self.up * probe_distance,
            ordered,
        )
        if hit is None or not hit.walkable:
            return None
        return hit

    def move(
        self,
        displacement: Vec3,
        bodies: tuple[RigidBody, ...] | list[RigidBody],
    ) -> CharacterMoveResult:
        if not isinstance(displacement, Vec3):
            raise PhysicsValidationError(
                "character displacement must be Vec3"
            )
        ordered = self._ordered_bodies(bodies)
        start = self.position
        remaining = displacement
        hits: list[CharacterSweepHit] = []
        grounded = False
        ground_normal: Vec3 | None = None
        stepped = False
        slides = 0

        for slide_index in range(self.settings.max_slides):
            if remaining.length() <= self.settings.min_move_distance:
                remaining = Vec3.zero()
                break
            slides = slide_index + 1
            hit = self._sweep_from(self.position, remaining, ordered)
            if hit is None:
                self.position = self.position + remaining
                remaining = Vec3.zero()
                break

            travel = remaining * hit.fraction
            self.position = self.position + travel
            hits.append(hit)

            if hit.walkable and remaining.dot(self.up) <= EPSILON:
                grounded = True
                ground_normal = hit.normal

            leftover = remaining * (1.0 - hit.fraction)
            if (
                not hit.walkable
                and not stepped
                and self.settings.step_height > 0.0
            ):
                step = self._try_step(leftover, ordered)
                if step is not None:
                    self.position, step_hits = step
                    hits.extend(step_hits)
                    grounded = True
                    ground_normal = step_hits[-1].normal
                    stepped = True
                    remaining = Vec3.zero()
                    break

            inward = leftover.dot(hit.normal)
            if inward < 0.0:
                leftover = leftover - hit.normal * inward

            if (
                hit.fraction <= EPSILON
                and leftover.length() >= remaining.length() - 1.0e-12
            ):
                remaining = Vec3.zero()
                break
            remaining = leftover

        if (
            not grounded
            and self.settings.snap_to_ground
            and self.settings.ground_probe_distance > 0.0
        ):
            probe = self._sweep_from(
                self.position,
                -self.up * self.settings.ground_probe_distance,
                ordered,
            )
            if probe is not None and probe.walkable:
                self.position = (
                    self.position
                    - self.up
                    * self.settings.ground_probe_distance
                    * probe.fraction
                )
                grounded = True
                ground_normal = probe.normal
                hits.append(probe)

        applied = self.position - start
        return CharacterMoveResult(
            start_position=start,
            position=self.position,
            requested_displacement=displacement,
            applied_displacement=applied,
            remaining_displacement=remaining,
            grounded=grounded,
            ground_normal=ground_normal,
            hits=tuple(hits),
            slide_iterations=slides,
            stepped=stepped,
        )
