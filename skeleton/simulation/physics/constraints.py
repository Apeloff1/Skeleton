"""Deterministic rigid-body constraints.

The first constraint primitive is a two-anchor distance joint. It is intentionally
small but establishes the architecture needed for hinges, sliders, motors, limits,
ragdolls, and articulated mechanisms without special-casing them inside contacts.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .body import BodyType, RigidBody
from .errors import BodyNotFoundError, PhysicsValidationError
from .math3d import EPSILON, Vec3

_JOINT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def _non_negative(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise PhysicsValidationError(f"{name} must be finite and non-negative")
    return value


@dataclass(frozen=True, slots=True)
class DistanceJoint:
    joint_id: str
    body_a: str
    body_b: str
    local_anchor_a: Vec3 = Vec3()
    local_anchor_b: Vec3 = Vec3()
    rest_length: float = 1.0
    bias_factor: float = 0.2

    def __post_init__(self) -> None:
        if not isinstance(self.joint_id, str) or not _JOINT_ID_RE.fullmatch(self.joint_id):
            raise PhysicsValidationError("invalid joint_id")
        if not self.body_a or not self.body_b or self.body_a == self.body_b:
            raise PhysicsValidationError("distance joint requires distinct body ids")
        if not isinstance(self.local_anchor_a, Vec3) or not isinstance(self.local_anchor_b, Vec3):
            raise PhysicsValidationError("joint anchors must be Vec3")
        rest_length = _non_negative(self.rest_length, name="rest_length")
        if rest_length <= EPSILON:
            raise PhysicsValidationError(
                "distance joint rest_length must be positive; use a point constraint for zero length"
            )
        object.__setattr__(self, "rest_length", rest_length)
        bias = _non_negative(self.bias_factor, name="bias_factor")
        if bias > 1.0:
            raise PhysicsValidationError("bias_factor must be in [0, 1]")
        object.__setattr__(self, "bias_factor", bias)

    def state_record(self) -> dict[str, object]:
        return {
            "joint_id": self.joint_id,
            "body_a": self.body_a,
            "body_b": self.body_b,
            "local_anchor_a": self.local_anchor_a.to_tuple(),
            "local_anchor_b": self.local_anchor_b.to_tuple(),
            "rest_length": self.rest_length,
            "bias_factor": self.bias_factor,
        }


@dataclass(frozen=True, slots=True)
class ConstraintStats:
    joints: int
    velocity_impulses: int
    position_corrections: int
    maximum_error: float


class ConstraintSolver:
    def __init__(
        self,
        *,
        velocity_iterations: int = 8,
        position_iterations: int = 4,
        position_slop: float = 0.001,
        position_correction: float = 0.65,
    ) -> None:
        for name, value in (
            ("velocity_iterations", velocity_iterations),
            ("position_iterations", position_iterations),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 128:
                raise PhysicsValidationError(f"{name} outside supported range")
        self.velocity_iterations = velocity_iterations
        self.position_iterations = position_iterations
        self.position_slop = _non_negative(position_slop, name="position_slop")
        self.position_correction = _non_negative(
            position_correction,
            name="position_correction",
        )
        if self.position_correction > 1.0:
            raise PhysicsValidationError("position_correction must be in [0, 1]")

    @staticmethod
    def _anchors(
        joint: DistanceJoint,
        body_a: RigidBody,
        body_b: RigidBody,
    ) -> tuple[Vec3, Vec3, Vec3, Vec3]:
        arm_a = body_a.orientation.rotate(joint.local_anchor_a)
        arm_b = body_b.orientation.rotate(joint.local_anchor_b)
        return (
            body_a.position + arm_a,
            body_b.position + arm_b,
            arm_a,
            arm_b,
        )

    @staticmethod
    def _effective_mass(body: RigidBody, arm: Vec3, axis: Vec3) -> float:
        if body.inverse_mass <= 0.0:
            return 0.0
        angular = body.world_inverse_inertia().mul_vec(arm.cross(axis)).cross(arm)
        return body.inverse_mass + axis.dot(angular)

    @staticmethod
    def _apply_impulse(
        body_a: RigidBody,
        body_b: RigidBody,
        impulse: Vec3,
        anchor_a: Vec3,
        anchor_b: Vec3,
    ) -> None:
        body_a.apply_impulse(-impulse, point=anchor_a)
        body_b.apply_impulse(impulse, point=anchor_b)

    def _validate_joint(
        self,
        joint: DistanceJoint,
        bodies: dict[str, RigidBody],
    ) -> tuple[RigidBody, RigidBody]:
        try:
            body_a = bodies[joint.body_a]
            body_b = bodies[joint.body_b]
        except KeyError as exc:
            raise BodyNotFoundError(str(exc)) from exc
        if body_a.body_type is BodyType.STATIC and body_b.body_type is BodyType.STATIC:
            raise PhysicsValidationError("distance joint cannot bind two static bodies")
        return body_a, body_b

    def solve(
        self,
        bodies: dict[str, RigidBody],
        joints: tuple[DistanceJoint, ...],
        *,
        dt: float,
    ) -> ConstraintStats:
        if isinstance(dt, bool) or not isinstance(dt, (int, float)):
            raise PhysicsValidationError("constraint dt must be numeric")
        dt = float(dt)
        if not math.isfinite(dt) or dt <= 0.0:
            raise PhysicsValidationError("constraint dt must be positive")

        ordered = tuple(sorted(joints, key=lambda row: row.joint_id))
        maximum_error = 0.0
        velocity_impulses = 0
        position_corrections = 0

        for joint in ordered:
            self._validate_joint(joint, bodies)

        for _ in range(self.velocity_iterations):
            for joint in ordered:
                body_a, body_b = self._validate_joint(joint, bodies)
                anchor_a, anchor_b, arm_a, arm_b = self._anchors(joint, body_a, body_b)
                delta = anchor_b - anchor_a
                length = delta.length()
                if length <= EPSILON:
                    axis = Vec3.axis(0)
                else:
                    axis = delta / length
                error = length - joint.rest_length
                maximum_error = max(maximum_error, abs(error))

                relative_velocity = (
                    body_b.velocity_at_world_point(anchor_b)
                    - body_a.velocity_at_world_point(anchor_a)
                ).dot(axis)
                denominator = (
                    self._effective_mass(body_a, arm_a, axis)
                    + self._effective_mass(body_b, arm_b, axis)
                )
                if denominator <= EPSILON:
                    continue

                bias = joint.bias_factor * error / dt
                impulse_magnitude = -(relative_velocity + bias) / denominator
                if not math.isfinite(impulse_magnitude):
                    raise PhysicsValidationError("distance joint produced non-finite impulse")
                if abs(impulse_magnitude) <= EPSILON:
                    continue
                self._apply_impulse(
                    body_a,
                    body_b,
                    axis * impulse_magnitude,
                    anchor_a,
                    anchor_b,
                )
                velocity_impulses += 1

        for _ in range(self.position_iterations):
            for joint in ordered:
                body_a, body_b = self._validate_joint(joint, bodies)
                anchor_a, anchor_b, _, _ = self._anchors(joint, body_a, body_b)
                delta = anchor_b - anchor_a
                length = delta.length()
                if length <= EPSILON:
                    continue
                axis = delta / length
                error = length - joint.rest_length
                maximum_error = max(maximum_error, abs(error))
                corrected_error = math.copysign(
                    max(0.0, abs(error) - self.position_slop),
                    error,
                )
                if abs(corrected_error) <= EPSILON:
                    continue

                inverse_mass_sum = body_a.inverse_mass + body_b.inverse_mass
                if inverse_mass_sum <= EPSILON:
                    continue
                magnitude = (
                    corrected_error
                    * (self.position_correction / self.position_iterations)
                    / inverse_mass_sum
                )
                correction = axis * magnitude
                if body_a.inverse_mass > 0.0:
                    body_a.position = body_a.position + correction * body_a.inverse_mass
                    body_a.wake()
                if body_b.inverse_mass > 0.0:
                    body_b.position = body_b.position - correction * body_b.inverse_mass
                    body_b.wake()
                position_corrections += 1

        return ConstraintStats(
            joints=len(ordered),
            velocity_impulses=velocity_impulses,
            position_corrections=position_corrections,
            maximum_error=maximum_error,
        )
