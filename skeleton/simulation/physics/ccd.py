"""Bounded continuous collision detection and deterministic TOI events.

Continuous sphere motion supports:
- sphere against static analytic sphere/box/plane geometry;
- sphere against moving static/kinematic/dynamic spheres using relative motion;
- global earliest-event selection with stable pair ordering.

The world consumes TOIEvent objects in bounded substeps so every body advances to
the same physical time before an impact is solved.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .body import BodyType, RigidBody
from .convex import gjk_distance
from .errors import PhysicsValidationError
from .math3d import EPSILON, Vec3
from .queries import Ray, RayHit, sphere_cast_body
from .shapes import (
    BoxShape,
    CapsuleShape,
    ConvexHullShape,
    CylinderShape,
    PlaneShape,
    SphereShape,
)

MAX_CCD_CHECKS = 1_000_000
MAX_CONVEX_TOI_ITERATIONS = 128


def _validate_dt(dt: float) -> float:
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise PhysicsValidationError("CCD dt must be numeric")
    dt = float(dt)
    if not math.isfinite(dt) or dt <= 0.0:
        raise PhysicsValidationError("CCD dt must be finite and positive")
    return dt


@dataclass(frozen=True, slots=True)
class CCDHit:
    """One moving-sphere sweep hit.

    normal points from the target toward the moving sphere at impact.  center is
    the moving sphere center at impact.
    """

    moving_body: str
    target_body: str
    fraction: float
    distance: float
    center: Vec3
    normal: Vec3

    def __post_init__(self) -> None:
        if self.moving_body == self.target_body:
            raise PhysicsValidationError("CCD hit requires distinct bodies")
        if not math.isfinite(self.fraction) or not 0.0 <= self.fraction <= 1.0:
            raise PhysicsValidationError("CCD fraction must be in [0, 1]")
        if not math.isfinite(self.distance) or self.distance < 0.0:
            raise PhysicsValidationError("CCD distance must be finite and non-negative")
        if not isinstance(self.center, Vec3):
            raise PhysicsValidationError("CCD center must be Vec3")
        object.__setattr__(self, "normal", self.normal.normalized())


@dataclass(frozen=True, slots=True)
class TOIEvent:
    """Canonical pair time-of-impact event.

    body_a/body_b are lexically ordered and normal points from body_a to body_b.
    """

    body_a: str
    body_b: str
    fraction: float
    time: float
    normal: Vec3

    def __post_init__(self) -> None:
        if not self.body_a or not self.body_b or self.body_a >= self.body_b:
            raise PhysicsValidationError("TOI body ids must be strictly ordered")
        if not math.isfinite(self.fraction) or not 0.0 <= self.fraction <= 1.0:
            raise PhysicsValidationError("TOI fraction must be in [0, 1]")
        if not math.isfinite(self.time) or self.time < 0.0:
            raise PhysicsValidationError("TOI time must be finite and non-negative")
        object.__setattr__(self, "normal", self.normal.normalized())


class ContinuousCollisionDetector:
    def __init__(
        self,
        *,
        motion_threshold: float = 0.5,
        max_checks: int = 65_536,
        convex_iterations: int = 32,
        distance_tolerance: float = 1.0e-6,
    ) -> None:
        if (
            isinstance(motion_threshold, bool)
            or not isinstance(motion_threshold, (int, float))
            or not math.isfinite(float(motion_threshold))
            or float(motion_threshold) <= 0.0
        ):
            raise PhysicsValidationError("CCD motion_threshold must be positive")
        if (
            isinstance(max_checks, bool)
            or not isinstance(max_checks, int)
            or not 1 <= max_checks <= MAX_CCD_CHECKS
        ):
            raise PhysicsValidationError("CCD max_checks outside supported range")
        if (
            isinstance(convex_iterations, bool)
            or not isinstance(convex_iterations, int)
            or not 1 <= convex_iterations <= MAX_CONVEX_TOI_ITERATIONS
        ):
            raise PhysicsValidationError(
                "CCD convex_iterations outside supported range"
            )
        if (
            isinstance(distance_tolerance, bool)
            or not isinstance(distance_tolerance, (int, float))
            or not math.isfinite(float(distance_tolerance))
            or float(distance_tolerance) <= 0.0
        ):
            raise PhysicsValidationError(
                "CCD distance_tolerance must be positive"
            )
        self.motion_threshold = float(motion_threshold)
        self.max_checks = max_checks
        self.convex_iterations = convex_iterations
        self.distance_tolerance = float(distance_tolerance)

    @staticmethod
    def _motion_radius(body: RigidBody) -> float:
        shape = body.shape
        if isinstance(shape, SphereShape):
            return shape.radius
        if isinstance(shape, BoxShape):
            return shape.half_extents.length()
        if isinstance(shape, CapsuleShape):
            return shape.half_height + shape.radius
        if isinstance(shape, CylinderShape):
            return math.sqrt(
                shape.radius * shape.radius
                + shape.half_height * shape.half_height
            )
        if isinstance(shape, ConvexHullShape):
            return max(vertex.length() for vertex in shape.vertices)
        raise PhysicsValidationError(
            "CCD motion radius requires finite convex shape"
        )

    @staticmethod
    def _finite_convex(body: RigidBody) -> bool:
        return isinstance(
            body.shape,
            (
                SphereShape,
                BoxShape,
                CapsuleShape,
                CylinderShape,
                ConvexHullShape,
            ),
        )

    def _eligible_continuous_body(self, body: RigidBody, dt: float) -> bool:
        if (
            not body.continuous
            or body.body_type is not BodyType.DYNAMIC
            or not body.awake
            or not self._finite_convex(body)
        ):
            return False
        radius = self._motion_radius(body)
        swept_motion = (
            body.linear_velocity.length()
            + body.angular_velocity.length() * radius
        ) * dt
        return swept_motion > radius * self.motion_threshold

    def _eligible_continuous_sphere(self, body: RigidBody, dt: float) -> bool:
        return (
            isinstance(body.shape, SphereShape)
            and self._eligible_continuous_body(body, dt)
        )

    @staticmethod
    def _sphere_sphere_toi(
        moving: RigidBody,
        target: RigidBody,
        dt: float,
    ) -> CCDHit | None:
        moving_shape = moving.shape
        target_shape = target.shape
        assert isinstance(moving_shape, SphereShape)
        assert isinstance(target_shape, SphereShape)

        relative_position = moving.position - target.position
        relative_velocity = moving.linear_velocity - target.linear_velocity
        radius = moving_shape.radius + target_shape.radius

        a = relative_velocity.length_squared()
        c = relative_position.length_squared() - radius * radius
        closing = relative_position.dot(relative_velocity)

        if c <= 0.0:
            if closing >= 0.0:
                return None
            normal = relative_position.normalized_or_zero()
            if normal.length_squared() <= EPSILON * EPSILON:
                normal = -relative_velocity.normalized_or_zero()
            if normal.length_squared() <= EPSILON * EPSILON:
                normal = Vec3.axis(0)
            return CCDHit(
                moving.body_id,
                target.body_id,
                0.0,
                0.0,
                moving.position,
                normal,
            )

        if a <= EPSILON * EPSILON or closing >= 0.0:
            return None

        discriminant = closing * closing - a * c
        if discriminant < 0.0:
            return None

        time = (-closing - math.sqrt(max(0.0, discriminant))) / a
        if time < 0.0 or time > dt:
            return None

        fraction = min(1.0, max(0.0, time / dt))
        center = moving.position + moving.linear_velocity * time
        target_center = target.position + target.linear_velocity * time
        normal = (center - target_center).normalized_or_zero()
        if normal.length_squared() <= EPSILON * EPSILON:
            normal = -relative_velocity.normalized_or_zero()
        if normal.length_squared() <= EPSILON * EPSILON:
            normal = Vec3.axis(0)
        return CCDHit(
            moving.body_id,
            target.body_id,
            fraction,
            moving.linear_velocity.length() * time,
            center,
            normal,
        )

    def _static_sweep(
        self,
        moving: RigidBody,
        target: RigidBody,
        dt: float,
    ) -> CCDHit | None:
        moving_shape = moving.shape
        assert isinstance(moving_shape, SphereShape)

        speed = moving.linear_velocity.length()
        travel = speed * dt
        if speed <= EPSILON:
            return None

        ray = Ray(moving.position, moving.linear_velocity / speed, travel)
        hit = sphere_cast_body(ray, moving_shape.radius, target)
        if hit is None:
            return None
        if (
            hit.distance <= EPSILON
            and moving.linear_velocity.dot(hit.normal) >= 0.0
        ):
            return None

        fraction = 0.0 if travel <= EPSILON else min(
            1.0,
            max(0.0, hit.distance / travel),
        )
        return CCDHit(
            moving.body_id,
            target.body_id,
            fraction,
            hit.distance,
            hit.point,
            hit.normal,
        )

    @staticmethod
    def _predicted_body(body: RigidBody, time: float) -> RigidBody:
        if body.body_type is BodyType.STATIC or time <= 0.0:
            return body
        orientation = body.orientation
        if body.angular_velocity.length_squared() > 0.0:
            orientation = orientation.integrate_world_angular_velocity(
                body.angular_velocity,
                time,
            )
        return replace(
            body,
            position=body.position + body.linear_velocity * time,
            orientation=orientation,
        )

    def _convex_toi(
        self,
        moving: RigidBody,
        target: RigidBody,
        dt: float,
    ) -> CCDHit | None:
        if not self._finite_convex(moving) or not self._finite_convex(target):
            return None

        radius_moving = self._motion_radius(moving)
        radius_target = self._motion_radius(target)
        time = 0.0
        previous_normal = Vec3.zero()
        time_tolerance = max(1.0e-12, dt * 1.0e-10)

        for _ in range(self.convex_iterations):
            predicted_moving = self._predicted_body(moving, time)
            predicted_target = self._predicted_body(target, time)
            distance = gjk_distance(
                predicted_moving,
                predicted_target,
                max_iterations=64,
                tolerance=max(
                    1.0e-10,
                    self.distance_tolerance * 0.1,
                ),
            )

            if (
                distance.intersects
                or distance.distance <= self.distance_tolerance
            ):
                moving_to_target = (
                    distance.normal
                    if distance.normal.length_squared() > EPSILON * EPSILON
                    else previous_normal
                )
                if moving_to_target.length_squared() <= EPSILON * EPSILON:
                    moving_to_target = (
                        predicted_target.position
                        - predicted_moving.position
                    ).normalized_or_zero()
                if moving_to_target.length_squared() <= EPSILON * EPSILON:
                    relative = (
                        target.linear_velocity - moving.linear_velocity
                    ).normalized_or_zero()
                    moving_to_target = (
                        relative
                        if relative.length_squared() > EPSILON * EPSILON
                        else Vec3.axis(0)
                    )

                target_to_moving = -moving_to_target
                relative_moving = (
                    moving.linear_velocity - target.linear_velocity
                )
                angular_bound = (
                    moving.angular_velocity.length() * radius_moving
                    + target.angular_velocity.length() * radius_target
                )
                if (
                    time <= time_tolerance
                    and relative_moving.dot(target_to_moving) >= 0.0
                    and angular_bound <= EPSILON
                ):
                    return None

                return CCDHit(
                    moving_body=moving.body_id,
                    target_body=target.body_id,
                    fraction=min(1.0, max(0.0, time / dt)),
                    distance=moving.linear_velocity.length() * time,
                    center=predicted_moving.position,
                    normal=target_to_moving,
                )

            previous_normal = distance.normal
            relative_velocity = (
                target.linear_velocity - moving.linear_velocity
            )
            linear_closing = max(
                0.0,
                -relative_velocity.dot(distance.normal),
            )
            angular_closing = (
                moving.angular_velocity.length() * radius_moving
                + target.angular_velocity.length() * radius_target
            )
            closing_bound = linear_closing + angular_closing
            if closing_bound <= EPSILON:
                return None

            advance = max(
                0.0,
                distance.distance - self.distance_tolerance,
            ) / closing_bound
            if advance <= time_tolerance:
                raise PhysicsValidationError(
                    "convex CCD failed to make progress"
                )
            time += advance
            if time > dt + time_tolerance:
                return None
            time = min(time, dt)

        raise PhysicsValidationError(
            "convex CCD iteration bound exceeded"
        )


    def _sweep_pair(
        self,
        moving: RigidBody,
        target: RigidBody,
        dt: float,
    ) -> CCDHit | None:
        if not self._eligible_continuous_body(moving, dt):
            return None

        if isinstance(moving.shape, SphereShape):
            if isinstance(target.shape, SphereShape):
                return self._sphere_sphere_toi(moving, target, dt)
            if (
                target.body_type is BodyType.STATIC
                and isinstance(
                    target.shape,
                    (BoxShape, CapsuleShape, CylinderShape, PlaneShape),
                )
            ):
                return self._static_sweep(moving, target, dt)

        if self._finite_convex(target):
            return self._convex_toi(moving, target, dt)
        return None

    def sweep(
        self,
        body: RigidBody,
        bodies: tuple[RigidBody, ...],
        dt: float,
    ) -> CCDHit | None:
        """Return the earliest sweep hit for one continuous dynamic convex body."""

        dt = _validate_dt(dt)
        if not self._eligible_continuous_body(body, dt):
            return None

        candidates: list[CCDHit] = []
        checks = 0
        for target in sorted(bodies, key=lambda row: row.body_id):
            if target.body_id == body.body_id:
                continue
            checks += 1
            if checks > self.max_checks:
                raise PhysicsValidationError("CCD check bound exceeded")
            hit = self._sweep_pair(body, target, dt)
            if hit is not None:
                candidates.append(hit)

        if not candidates:
            return None
        return min(
            candidates,
            key=lambda row: (
                row.fraction,
                row.target_body,
                row.moving_body,
            ),
        )

    @staticmethod
    def _canonical_event(hit: CCDHit, dt: float) -> TOIEvent:
        if hit.moving_body < hit.target_body:
            body_a = hit.moving_body
            body_b = hit.target_body
            normal = -hit.normal
        else:
            body_a = hit.target_body
            body_b = hit.moving_body
            normal = hit.normal
        return TOIEvent(
            body_a=body_a,
            body_b=body_b,
            fraction=hit.fraction,
            time=hit.fraction * dt,
            normal=normal,
        )

    def earliest_event(
        self,
        bodies: tuple[RigidBody, ...],
        dt: float,
    ) -> TOIEvent | None:
        """Return one stable earliest TOI across all eligible continuous pairs."""

        dt = _validate_dt(dt)
        ordered = tuple(sorted(bodies, key=lambda row: row.body_id))
        events: dict[tuple[str, str], TOIEvent] = {}
        checks = 0

        visited_pairs: set[tuple[str, str]] = set()
        for moving in ordered:
            if not self._eligible_continuous_body(moving, dt):
                continue
            for target in ordered:
                if target.body_id == moving.body_id:
                    continue

                pair = tuple(sorted((moving.body_id, target.body_id)))
                if pair in visited_pairs:
                    continue
                visited_pairs.add(pair)

                checks += 1
                if checks > self.max_checks:
                    raise PhysicsValidationError("CCD check bound exceeded")
                hit = self._sweep_pair(moving, target, dt)
                if hit is None:
                    continue
                event = self._canonical_event(hit, dt)
                existing = events.get((event.body_a, event.body_b))
                if existing is None or (
                    event.fraction,
                    event.body_a,
                    event.body_b,
                ) < (
                    existing.fraction,
                    existing.body_a,
                    existing.body_b,
                ):
                    events[(event.body_a, event.body_b)] = event

        if not events:
            return None
        return min(
            events.values(),
            key=lambda row: (
                row.fraction,
                row.body_a,
                row.body_b,
            ),
        )
