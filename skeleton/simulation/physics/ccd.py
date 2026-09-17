"""Bounded continuous collision detection for high-speed dynamic spheres.

This first CCD slice is deliberately conservative and exact about its supported
domain: dynamic spheres sweep against static analytic sphere/box/plane targets.
It prevents the common game failure mode where a projectile crosses a thin
collider in one fixed step. Dynamic-vs-dynamic conservative advancement remains
a later layer.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import BodyType, RigidBody
from .errors import PhysicsValidationError
from .math3d import EPSILON, Vec3
from .queries import Ray, RayHit, sphere_cast_body
from .shapes import SphereShape

MAX_CCD_CHECKS = 1_000_000


@dataclass(frozen=True, slots=True)
class CCDHit:
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

    def sweep(
        self,
        body: RigidBody,
        bodies: tuple[RigidBody, ...],
        dt: float,
    ) -> CCDHit | None:
        if not body.continuous or body.body_type is not BodyType.DYNAMIC:
            return None
        if not isinstance(body.shape, SphereShape):
            return None
        if isinstance(dt, bool) or not isinstance(dt, (int, float)):
            raise PhysicsValidationError("CCD dt must be numeric")
        dt = float(dt)
        if not math.isfinite(dt) or dt <= 0.0:
            raise PhysicsValidationError("CCD dt must be finite and positive")

        speed = body.linear_velocity.length()
        travel = speed * dt
        threshold = body.shape.radius * self.motion_threshold
        if speed <= EPSILON or travel <= threshold:
            return None

        ray = Ray(body.position, body.linear_velocity / speed, travel)
        candidates: list[tuple[float, str, RayHit]] = []
        checks = 0
        for target in sorted(bodies, key=lambda row: row.body_id):
            if target.body_id == body.body_id:
                continue
            if target.body_type is not BodyType.STATIC:
                continue
            checks += 1
            if checks > self.max_checks:
                raise PhysicsValidationError("CCD check bound exceeded")
            hit = sphere_cast_body(ray, body.shape.radius, target)
            if hit is not None:
                candidates.append((hit.distance, target.body_id, hit))

        if not candidates:
            return None
        distance, target_id, hit = min(candidates, key=lambda row: (row[0], row[1]))
        fraction = 0.0 if travel <= EPSILON else min(1.0, max(0.0, distance / travel))
        return CCDHit(
            moving_body=body.body_id,
            target_body=target_id,
            fraction=fraction,
            distance=distance,
            center=hit.point,
            normal=hit.normal,
        )
