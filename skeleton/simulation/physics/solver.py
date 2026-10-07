"""Sequential impulse contact solver with persistent warm starting."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .body import RigidBody
from .collision import ContactManifold, ContactPoint
from .contacts import ContactCache
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
    warm_started_contacts: int = 0
    cached_contacts: int = 0


@dataclass(slots=True)
class _VelocityContact:
    manifold: ContactManifold
    point: ContactPoint
    accumulated_normal: float = 0.0
    tangent: Vec3 = Vec3()
    accumulated_tangent: float = 0.0
    restitution_target: float = 0.0


class SequentialImpulseSolver:
    """Deterministic projected Gauss-Seidel contact solver.

    Normal and tangential impulses are accumulated and clamped across iterations.
    When a bounded ContactCache is supplied, the prior frame's converged impulses
    are applied once before iteration, substantially improving resting stacks and
    low-iteration stability without hiding solver state from determinism.
    """

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

    def _prepare_contacts(
        self,
        bodies: dict[str, RigidBody],
        manifolds: tuple[ContactManifold, ...],
        *,
        cache: ContactCache | None,
        tick: int,
    ) -> tuple[list[_VelocityContact], int]:
        states: list[_VelocityContact] = []
        warm_started = 0

        for manifold in manifolds:
            body_a = bodies[manifold.body_a]
            body_b = bodies[manifold.body_b]
            for point in manifold.points:
                relative, _, _ = self._relative_velocity(body_a, body_b, point.position)
                normal_speed = relative.dot(manifold.normal)
                restitution_target = (
                    -manifold.material.restitution * normal_speed
                    if normal_speed < -self.restitution_velocity_threshold
                    else 0.0
                )
                slip = relative - manifold.normal * normal_speed
                tangent = slip.normalized_or_zero()
                state = _VelocityContact(
                    manifold=manifold,
                    point=point,
                    tangent=tangent,
                    restitution_target=restitution_target,
                )

                entry = None if cache is None else cache.lookup(manifold, point, tick=tick)
                if entry is not None:
                    state.accumulated_normal = entry.normal_impulse
                    if entry.tangent.length_squared() > EPSILON * EPSILON:
                        projected = (
                            entry.tangent
                            - manifold.normal * entry.tangent.dot(manifold.normal)
                        )
                        if projected.length_squared() > EPSILON * EPSILON:
                            state.tangent = projected.normalized()
                            state.accumulated_tangent = entry.tangent_impulse

                    both_quiet = (
                        (not body_a.dynamic_body or not body_a.awake)
                        and (not body_b.dynamic_body or not body_b.awake)
                    )
                    if not both_quiet:
                        impulse = (
                            manifold.normal * state.accumulated_normal
                            + state.tangent * state.accumulated_tangent
                        )
                        if impulse.length_squared() > EPSILON * EPSILON:
                            self._apply_pair_impulse(
                                body_a,
                                body_b,
                                impulse,
                                point.position,
                            )
                            warm_started += 1
                states.append(state)

        return states, warm_started

    def _solve_normal(
        self,
        bodies: dict[str, RigidBody],
        state: _VelocityContact,
    ) -> int:
        manifold = state.manifold
        point = state.point
        body_a = bodies[manifold.body_a]
        body_b = bodies[manifold.body_b]
        relative, arm_a, arm_b = self._relative_velocity(body_a, body_b, point.position)
        normal = manifold.normal
        normal_speed = relative.dot(normal)

        denominator = (
            self._effective_mass(body_a, arm_a, normal)
            + self._effective_mass(body_b, arm_b, normal)
        )
        if denominator <= EPSILON:
            return 0

        delta = -(normal_speed - state.restitution_target) / denominator
        if not math.isfinite(delta):
            raise SolverError("non-finite normal impulse")
        previous = state.accumulated_normal
        state.accumulated_normal = max(0.0, previous + delta)
        applied = state.accumulated_normal - previous
        if abs(applied) <= EPSILON:
            return 0

        self._apply_pair_impulse(
            body_a,
            body_b,
            normal * applied,
            point.position,
        )
        return 1

    def _solve_friction(
        self,
        bodies: dict[str, RigidBody],
        state: _VelocityContact,
    ) -> int:
        if state.accumulated_normal <= EPSILON:
            return 0

        manifold = state.manifold
        point = state.point
        body_a = bodies[manifold.body_a]
        body_b = bodies[manifold.body_b]
        relative, arm_a, arm_b = self._relative_velocity(body_a, body_b, point.position)
        normal = manifold.normal
        slip = relative - normal * relative.dot(normal)

        if state.tangent.length_squared() <= EPSILON * EPSILON:
            if slip.length_squared() <= EPSILON * EPSILON:
                return 0
            state.tangent = slip.normalized()

        tangent = state.tangent
        denominator = (
            self._effective_mass(body_a, arm_a, tangent)
            + self._effective_mass(body_b, arm_b, tangent)
        )
        if denominator <= EPSILON:
            return 0

        delta = -relative.dot(tangent) / denominator
        if not math.isfinite(delta):
            raise SolverError("non-finite friction impulse")

        friction_limit = manifold.material.friction * state.accumulated_normal
        previous = state.accumulated_tangent
        state.accumulated_tangent = min(
            max(previous + delta, -friction_limit),
            friction_limit,
        )
        applied = state.accumulated_tangent - previous
        if abs(applied) <= EPSILON:
            return 0

        self._apply_pair_impulse(
            body_a,
            body_b,
            tangent * applied,
            point.position,
        )
        return 1

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
        *,
        cache: ContactCache | None = None,
        tick: int = 0,
    ) -> SolverStats:
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise PhysicsValidationError("solver tick must be non-negative integer")

        states, warm_started = self._prepare_contacts(
            bodies,
            manifolds,
            cache=cache,
            tick=tick,
        )
        normal_impulses = 0
        friction_impulses = 0
        position_corrections = 0
        maximum_penetration = max((row.penetration for row in manifolds), default=0.0)

        for _ in range(self.velocity_iterations):
            for state in states:
                normal_impulses += self._solve_normal(bodies, state)
                friction_impulses += self._solve_friction(bodies, state)

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

        if cache is not None:
            for state in states:
                cache.store(
                    state.manifold,
                    state.point,
                    normal_impulse=state.accumulated_normal,
                    tangent=state.tangent,
                    tangent_impulse=state.accumulated_tangent,
                    tick=tick,
                )
            cache.prune(tick=tick)

        return SolverStats(
            velocity_iterations=self.velocity_iterations,
            position_iterations=self.position_iterations,
            normal_impulses=normal_impulses,
            friction_impulses=friction_impulses,
            position_corrections=position_corrections,
            maximum_penetration=maximum_penetration,
            warm_started_contacts=warm_started,
            cached_contacts=0 if cache is None else len(cache),
        )
