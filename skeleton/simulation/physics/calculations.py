"""Physical calculations and system-level diagnostics.

These functions are side-effect free and use the same rigid-body state as the
solver.  They provide conservation diagnostics, gameplay telemetry, tests, and
future promotion gates for more advanced solver implementations.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import BodyType, RigidBody
from .errors import PhysicsValidationError
from .math3d import Vec3


@dataclass(frozen=True, slots=True)
class PhysicsAggregate:
    dynamic_bodies: int
    total_mass: float
    center_of_mass: Vec3
    linear_momentum: Vec3
    angular_momentum: Vec3
    kinetic_energy: float
    potential_energy: float

    @property
    def mechanical_energy(self) -> float:
        return self.kinetic_energy + self.potential_energy


def world_inertia(body: RigidBody):
    """Return the body inertia tensor expressed in world coordinates."""

    if body.body_type is not BodyType.DYNAMIC:
        return body.local_inertia
    rotation = body.orientation.to_matrix()
    return rotation.mul_mat(body.local_inertia).mul_mat(rotation.transpose())


def linear_momentum(body: RigidBody) -> Vec3:
    if body.body_type is not BodyType.DYNAMIC:
        return Vec3.zero()
    return body.linear_velocity * body.mass


def angular_momentum(body: RigidBody, *, origin: Vec3 = Vec3()) -> Vec3:
    """Angular momentum about an arbitrary world-space origin."""

    if not isinstance(origin, Vec3):
        raise PhysicsValidationError("origin must be Vec3")
    if body.body_type is not BodyType.DYNAMIC:
        return Vec3.zero()
    intrinsic = world_inertia(body).mul_vec(body.angular_velocity)
    orbital = (body.position - origin).cross(linear_momentum(body))
    return intrinsic + orbital


def kinetic_energy(body: RigidBody) -> float:
    if body.body_type is not BodyType.DYNAMIC:
        return 0.0
    linear = 0.5 * body.mass * body.linear_velocity.length_squared()
    rotational = 0.5 * body.angular_velocity.dot(
        world_inertia(body).mul_vec(body.angular_velocity)
    )
    return linear + rotational


def gravitational_potential_energy(
    body: RigidBody,
    gravity: Vec3,
    *,
    reference: Vec3 = Vec3(),
) -> float:
    """Potential energy for a uniform gravity field: U = -m g·(r-r0)."""

    if not isinstance(gravity, Vec3) or not isinstance(reference, Vec3):
        raise PhysicsValidationError("gravity and reference must be Vec3")
    if body.body_type is not BodyType.DYNAMIC:
        return 0.0
    displacement = body.position - reference
    return -body.mass * gravity.dot(displacement)


def impulse_from_force(force: Vec3, dt: float) -> Vec3:
    if not isinstance(force, Vec3):
        raise PhysicsValidationError("force must be Vec3")
    if isinstance(dt, bool) or not isinstance(dt, (int, float)):
        raise PhysicsValidationError("dt must be numeric")
    dt = float(dt)
    if not math.isfinite(dt) or dt < 0.0:
        raise PhysicsValidationError("dt must be finite and non-negative")
    return force * dt


def aggregate_physics(
    bodies: tuple[RigidBody, ...],
    gravity: Vec3,
    *,
    angular_origin: Vec3 = Vec3(),
    potential_reference: Vec3 = Vec3(),
) -> PhysicsAggregate:
    if not isinstance(gravity, Vec3):
        raise PhysicsValidationError("gravity must be Vec3")
    if not isinstance(angular_origin, Vec3) or not isinstance(potential_reference, Vec3):
        raise PhysicsValidationError("reference points must be Vec3")

    dynamic = tuple(
        body
        for body in sorted(bodies, key=lambda row: row.body_id)
        if body.body_type is BodyType.DYNAMIC
    )
    total_mass = sum(body.mass for body in dynamic)

    weighted_position = Vec3.zero()
    total_linear_momentum = Vec3.zero()
    total_angular_momentum = Vec3.zero()
    total_kinetic = 0.0
    total_potential = 0.0

    for body in dynamic:
        weighted_position = weighted_position + body.position * body.mass
        total_linear_momentum = total_linear_momentum + linear_momentum(body)
        total_angular_momentum = total_angular_momentum + angular_momentum(
            body,
            origin=angular_origin,
        )
        total_kinetic += kinetic_energy(body)
        total_potential += gravitational_potential_energy(
            body,
            gravity,
            reference=potential_reference,
        )

    center = Vec3.zero() if total_mass == 0.0 else weighted_position / total_mass
    return PhysicsAggregate(
        dynamic_bodies=len(dynamic),
        total_mass=total_mass,
        center_of_mass=center,
        linear_momentum=total_linear_momentum,
        angular_momentum=total_angular_momentum,
        kinetic_energy=total_kinetic,
        potential_energy=total_potential,
    )
