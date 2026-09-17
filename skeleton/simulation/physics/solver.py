"""Velocity and positional contact resolution using sequential impulses."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import RigidBody
from .collision import ContactManifold, ContactPoint
from .errors import PhysicsValidationError, SolverError
from .math3d import EPSILON, Vec3


def _positive_int(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PhysicsValidationError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class SolverStats:
    velocity_iterations: int
    position_iterations: int
    normal_impulses: int
    friction_impulses: int
    position_corrections: int
    maximum_penetration: float


class SequentialImpulseSolver:
    """Deterministic Gauss-Seidel-style rigid-body contact solver."""

    def __init__(
        self,
        *,
        velocity_iterations: int = 10,
        position_iterations: int = 4,
        penetration_slop: float = 0.002,
        position_correction: float = 0.65,
        restitution_velocity_threshold: float = 0.5,
    ) -> None:
        self.velocity_iterations = _positive_int(velocity_iterations, name="velocity_iterations")
        self.position_iterations = _positive_int(position_iterations, name="position_iterations")
        self.penetration_slop = self._coefficient(
            penetration_slop,
            name="penetration_slop",
            maximum=None,
        )
        self.position_correction = self._coefficient(
            position_correction,
            name="position_correction",
            maximum=1.0,
        )
        self.restitution_velocity_threshold = self._coefficient(
            restitution_velocity_threshold,
            name="restitution_velocity_threshold",
            maximum=None,
        )

    @staticmethod
    def _coefficient(value: float, *, name: str, maximum: float | None) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PhysicsValidationError(f"{name} must be numeric")
        value = float(value)
        if not math.isfinite(value) or value < 0.0 or (maximum is not None and value > maximum):
            raise PhysicsValidationError(f"invalid {name}")
        return value

    @staticmethod
    def _effective_mass(body: RigidBody, arm: Vec3, axis: Vec3) -> float:
        if body.inverse_mass <= 0.0:
            return 0.0
        angular = body.world_inverse_inertia().mul_vec(arm.cross(axis)).cross(arm)
        return body.inverse_mass + axis.dot(angular)

    @staticmethod
    def _relative_velocity(
        body_a: RigidBody,
        body_b: RigidBody,
        point: Vec3,
    ) -> tuple[Vec3, Vec3, Vec3]:
        arm_a = point - body_a.position
        arm_b = point - body_b.position
        velocity_a = body_a.velocity_at_world_point(point)
        velocity_b = body_b.velocity_at_world_point(point)
        return velocity_b - velocity_a, arm_a, arm_b

    @staticmethod
    def _apply_pair_impulse(
        body_a: RigidBody,
        body_b: RigidBody,
        impulse: Vec3,
        point: Vec3,
    ) -> None:
        body_a.apply_impulse(-impulse, point=point)
        body_b.apply_impulse(impulse, point=point)

    def _solve_velocity_point(
        self,
        body_a: RigidBody,
        body_b: RigidBody,
        manifold: ContactManifold,
        point: ContactPoint,
    ) -> tuple[int, int]:
        relative, arm_a, arm_b = self._relative_velocity(body_a, body_b, point.position)
        normal = manifold.normal
        normal_speed = relative.dot(normal)

        if normal_speed >= 0.0:
            return (0, 0)

        restitution = (
            manifold.material.restitution
            if normal_speed < -self.restitution_velocity_threshold
            else 0.0
        )
        denominator = (
            self._effective_mass(body_a, arm_a, normal)
            + self._effective_mass(body_b, arm_b, normal)
        )
        if denominator <= EPSILON:
            return (0, 0)

        normal_impulse_magnitude = -(1.0 + restitution) * normal_speed / denominator
        if not math.isfinite(normal_impulse_magnitude):
            raise SolverError("non-finite normal impulse")
        normal_impulse_magnitude = max(0.0, normal_impulse_magnitude)
        normal_impulse = normal * normal_impulse_magnitude
        self._apply_pair_impulse(body_a, body_b, normal_impulse, point.position)

        relative_after, arm_a, arm_b = self._relative_velocity(body_a, body_b, point.position)
        tangent = relative_after - normal * relative_after.dot(normal)
        if tangent.length_squared() <= EPSILON * EPSILON:
            return (1, 0)
        tangent = tangent.normalized()

        tangent_denominator = (
            self._effective_mass(body_a, arm_a, tangent)
            + self._effective_mass(body_b, arm_b, tangent)
        )
        if tangent_denominator <= EPSILON:
            return (1, 0)

        friction_magnitude = -relative_after.dot(tangent) / tangent_denominator
        friction_limit = manifold.material.friction * normal_impulse_magnitude
        friction_magnitude = min(max(friction_magnitude, -friction_limit), friction_limit)
        if abs(friction_magnitude) <= EPSILON:
            return (1, 0)

        self._apply_pair_impulse(
            body_a,
            body_b,
            tangent * friction_magnitude,
            point.position,
        )
        return (1, 1)

    def _solve_position_point(
        self,
        body_a: RigidBody,
        body_b: RigidBody,
        manifold: ContactManifold,
        point: ContactPoint,
    ) -> int:
        penetration = max(0.0, point.penetration - self.penetration_slop)
        if penetration <= 0.0:
            return 0

        inverse_mass_sum = body_a.inverse_mass + body_b.inverse_mass
        if inverse_mass_sum <= EPSILON:
            return 0

        fraction = self.position_correction / self.position_iterations
        magnitude = penetration * fraction / inverse_mass_sum
        correction = manifold.normal * magnitude

        if body_a.inverse_mass > 0.0:
            body_a.position = body_a.position - correction * body_a.inverse_mass
            body_a.wake()
        if body_b.inverse_mass > 0.0:
            body_b.position = body_b.position + correction * body_b.inverse_mass
            body_b.wake()
        return 1

    def solve(
        self,
        bodies: dict[str, RigidBody],
        manifolds: tuple[ContactManifold, ...],
    ) -> SolverStats:
        normal_impulses = 0
        friction_impulses = 0
        position_corrections = 0
        maximum_penetration = max((row.penetration for row in manifolds), default=0.0)

        for _ in range(self.velocity_iterations):
            for manifold in manifolds:
                body_a = bodies[manifold.body_a]
                body_b = bodies[manifold.body_b]
                for point in manifold.points:
                    normal_count, friction_count = self._solve_velocity_point(
                        body_a,
                        body_b,
                        manifold,
                        point,
                    )
                    normal_impulses += normal_count
                    friction_impulses += friction_count

        for _ in range(self.position_iterations):
            for manifold in manifolds:
                body_a = bodies[manifold.body_a]
                body_b = bodies[manifold.body_b]
                for point in manifold.points:
                    position_corrections += self._solve_position_point(
                        body_a,
                        body_b,
                        manifold,
                        point,
                    )

        return SolverStats(
            velocity_iterations=self.velocity_iterations,
            position_iterations=self.position_iterations,
            normal_impulses=normal_impulses,
            friction_impulses=friction_impulses,
            position_corrections=position_corrections,
            maximum_penetration=maximum_penetration,
        )
