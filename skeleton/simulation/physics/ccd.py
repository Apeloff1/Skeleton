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
from dataclasses import dataclass

from .body import BodyType, RigidBody
from .convex import convex_plane_time_of_impact, convex_time_of_impact
from .errors import PhysicsValidationError
from .math3d import EPSILON, Vec3
from .queries import Ray, RayHit, sphere_cast_body
from .shapes import (
    BoxShape,
    CapsuleShape,
    CylinderShape,
    PlaneShape,
    SphereShape,
)

MAX_CCD_CHECKS = 1_000_000


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
        self.motion_threshold = float(motion_threshold)
        self.max_checks = max_checks

    @staticmethod
    def _finite_sweep_radius(body: RigidBody) -> float | None:
        shape = body.shape
        if isinstance(shape, SphereShape):
            return shape.radius
        if isinstance(shape, BoxShape):
            return shape.half_extents.length()
        if isinstance(shape, CapsuleShape):
            return shape.half_height + shape.radius
        if isinstance(shape, CylinderShape):
            return math.hypot(shape.radius, shape.half_height)
        return None

    def _eligible_continuous_body(self, body: RigidBody, dt: float) -> bool:
        if (
            not body.continuous
            or body.body_type is not BodyType.DYNAMIC
            or not body.awake
        ):
            return False
        radius = self._finite_sweep_radius(body)
        if radius is None:
            return False
        motion = body.linear_velocity.length() * dt
        if not isinstance(body.shape, SphereShape):
            motion += body.angular_velocity.length() * radius * dt
        return motion > radius * self.motion_threshold

    @staticmethod
    def _continuous_finite_body(body: RigidBody) -> bool:
        return (
            body.continuous
            and body.body_type is BodyType.DYNAMIC
            and body.awake
            and isinstance(
                body.shape,
                (SphereShape, BoxShape, CapsuleShape, CylinderShape),
            )
        )

    def _pair_requires_general_ccd(
        self,
        body_a: RigidBody,
        body_b: RigidBody,
        dt: float,
    ) -> bool:
        continuous = tuple(
            body
            for body in (body_a, body_b)
            if self._continuous_finite_body(body)
        )
        if not continuous:
            return False

        relative_travel = (
            body_b.linear_velocity - body_a.linear_velocity
        ).length() * dt

        angular_travel = 0.0
        for body in (body_a, body_b):
            radius = self._finite_sweep_radius(body)
            if radius is not None:
                angular_travel += (
                    body.angular_velocity.length() * radius * dt
                )

        threshold_radius = min(
            radius
            for body in continuous
            if (radius := self._finite_sweep_radius(body)) is not None
        )
        return (
            relative_travel + angular_travel
            > threshold_radius * self.motion_threshold
        )

    def _eligible_continuous_sphere(self, body: RigidBody, dt: float) -> bool:
        if (
            not body.continuous
            or body.body_type is not BodyType.DYNAMIC
            or not isinstance(body.shape, SphereShape)
            or not body.awake
        ):
            return False
        travel = body.linear_velocity.length() * dt
        return travel > body.shape.radius * self.motion_threshold

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

    def _sweep_pair(
        self,
        moving: RigidBody,
        target: RigidBody,
        dt: float,
    ) -> CCDHit | None:
        if not self._eligible_continuous_sphere(moving, dt):
            return None
        assert isinstance(moving.shape, SphereShape)

        if isinstance(target.shape, SphereShape):
            return self._sphere_sphere_toi(moving, target, dt)

        if target.body_type is not BodyType.STATIC:
            return None
        if isinstance(
            target.shape,
            (BoxShape, CapsuleShape, CylinderShape, PlaneShape),
        ):
            return self._static_sweep(moving, target, dt)
        return None

    def sweep(
        self,
        body: RigidBody,
        bodies: tuple[RigidBody, ...],
        dt: float,
    ) -> CCDHit | None:
        """Return the earliest sweep hit for one continuous dynamic sphere."""

        dt = _validate_dt(dt)
        if not self._eligible_continuous_sphere(body, dt):
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

        for moving in ordered:
            if not self._eligible_continuous_sphere(moving, dt):
                continue
            for target in ordered:
                if target.body_id == moving.body_id:
                    continue

                pair = tuple(sorted((moving.body_id, target.body_id)))
                if pair in events and isinstance(target.shape, SphereShape):
                    # A two-continuous-sphere pair may be visited in both
                    # directions. One canonical event is sufficient.
                    continue

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

        finite_shapes = (
            SphereShape,
            BoxShape,
            CapsuleShape,
            CylinderShape,
        )
        for index, body_a in enumerate(ordered):
            for body_b in ordered[index + 1 :]:
                pair = (body_a.body_id, body_b.body_id)
                if pair in events:
                    continue
                if not self._pair_requires_general_ccd(
                    body_a,
                    body_b,
                    dt,
                ):
                    continue
                if not isinstance(body_a.shape, finite_shapes) or not isinstance(
                    body_b.shape,
                    finite_shapes,
                ):
                    continue

                checks += 1
                if checks > self.max_checks:
                    raise PhysicsValidationError("CCD check bound exceeded")

                hit = convex_time_of_impact(
                    body_a,
                    body_b,
                    dt,
                    max_iterations=128,
                    distance_iterations=64,
                    distance_tolerance=1.0e-6,
                    time_tolerance=1.0e-9,
                )
                if hit is None:
                    continue

                if hit.time <= EPSILON:
                    relative_velocity = (
                        body_b.velocity_at_world_point(hit.point_b)
                        - body_a.velocity_at_world_point(hit.point_a)
                    )
                    if relative_velocity.dot(hit.normal) >= -EPSILON:
                        continue

                event = TOIEvent(
                    body_a=body_a.body_id,
                    body_b=body_b.body_id,
                    fraction=hit.fraction,
                    time=hit.time,
                    normal=hit.normal,
                )
                events[pair] = event

        for convex in ordered:
            if not self._continuous_finite_body(convex):
                continue

            for plane in ordered:
                if plane.body_id == convex.body_id:
                    continue
                if not isinstance(plane.shape, PlaneShape):
                    continue

                pair = tuple(
                    sorted((convex.body_id, plane.body_id))
                )
                if pair in events:
                    # Exact sphere/static-plane sweeps and any earlier
                    # canonical event remain authoritative.
                    continue
                if not self._pair_requires_general_ccd(
                    convex,
                    plane,
                    dt,
                ):
                    continue

                checks += 1
                if checks > self.max_checks:
                    raise PhysicsValidationError(
                        "CCD check bound exceeded"
                    )

                hit = convex_plane_time_of_impact(
                    convex,
                    plane,
                    dt,
                    max_iterations=64,
                    distance_tolerance=1.0e-6,
                    time_tolerance=1.0e-9,
                )
                if hit is None:
                    continue

                if hit.time <= EPSILON:
                    relative_velocity = (
                        plane.velocity_at_world_point(hit.point_b)
                        - convex.velocity_at_world_point(hit.point_a)
                    )
                    if (
                        relative_velocity.dot(hit.normal)
                        >= -EPSILON
                    ):
                        continue

                if convex.body_id < plane.body_id:
                    normal = hit.normal
                else:
                    normal = -hit.normal

                event = TOIEvent(
                    body_a=pair[0],
                    body_b=pair[1],
                    fraction=hit.fraction,
                    time=hit.time,
                    normal=normal,
                )
                events[pair] = event

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
