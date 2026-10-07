"""Rigid-body state and Newton-Euler integration primitives."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .errors import PhysicsValidationError
from .materials import PhysicsMaterial
from .math3d import Mat3, Quat, Transform, Vec3
from .shapes import CollisionShape

_BODY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class BodyType(str, Enum):
    STATIC = "static"
    KINEMATIC = "kinematic"
    DYNAMIC = "dynamic"


def _non_negative(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < 0.0:
        raise PhysicsValidationError(f"{name} must be finite and non-negative")
    return value


@dataclass(slots=True)
class RigidBody:
    body_id: str
    shape: CollisionShape
    body_type: BodyType = BodyType.STATIC
    position: Vec3 = Vec3()
    orientation: Quat = Quat()
    linear_velocity: Vec3 = Vec3()
    angular_velocity: Vec3 = Vec3()
    material: PhysicsMaterial = PhysicsMaterial()
    mass: float = math.inf
    inverse_mass: float = 0.0
    local_inertia: Mat3 = field(default_factory=Mat3.zero)
    local_inverse_inertia: Mat3 = field(default_factory=Mat3.zero)
    linear_damping: float = 0.05
    angular_damping: float = 0.05
    gravity_scale: float = 1.0
    force: Vec3 = Vec3()
    torque: Vec3 = Vec3()
    awake: bool = True
    sleep_time: float = 0.0
    continuous: bool = False
    user_data: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.body_id, str) or not _BODY_ID_RE.fullmatch(self.body_id):
            raise PhysicsValidationError("invalid body_id")
        if not isinstance(self.body_type, BodyType):
            raise PhysicsValidationError("body_type must be BodyType")
        if not isinstance(self.shape, CollisionShape):
            raise PhysicsValidationError("shape must satisfy CollisionShape")
        if not isinstance(self.position, Vec3):
            raise PhysicsValidationError("position must be Vec3")
        if not isinstance(self.orientation, Quat):
            raise PhysicsValidationError("orientation must be Quat")
        if not isinstance(self.linear_velocity, Vec3):
            raise PhysicsValidationError("linear_velocity must be Vec3")
        if not isinstance(self.angular_velocity, Vec3):
            raise PhysicsValidationError("angular_velocity must be Vec3")
        if not isinstance(self.force, Vec3):
            raise PhysicsValidationError("force must be Vec3")
        if not isinstance(self.torque, Vec3):
            raise PhysicsValidationError("torque must be Vec3")
        if not isinstance(self.material, PhysicsMaterial):
            raise PhysicsValidationError("material must be PhysicsMaterial")
        if not isinstance(self.local_inertia, Mat3) or not isinstance(self.local_inverse_inertia, Mat3):
            raise PhysicsValidationError("inertia tensors must be Mat3")
        if not isinstance(self.awake, bool):
            raise PhysicsValidationError("awake must be boolean")
        if not isinstance(self.continuous, bool):
            raise PhysicsValidationError("continuous must be boolean")
        self.orientation = self.orientation.normalized()
        self.linear_damping = _non_negative(self.linear_damping, name="linear_damping")
        self.angular_damping = _non_negative(self.angular_damping, name="angular_damping")
        self.gravity_scale = _non_negative(self.gravity_scale, name="gravity_scale")
        self.sleep_time = _non_negative(self.sleep_time, name="sleep_time")
        if self.body_type is BodyType.DYNAMIC:
            if not math.isfinite(self.mass) or self.mass <= 0.0:
                raise PhysicsValidationError("dynamic body mass must be finite and positive")
            if not math.isfinite(self.inverse_mass) or self.inverse_mass <= 0.0:
                raise PhysicsValidationError("dynamic body inverse_mass must be positive")
            if not math.isclose(
                self.inverse_mass,
                1.0 / self.mass,
                rel_tol=1.0e-9,
                abs_tol=1.0e-12,
            ):
                raise PhysicsValidationError("dynamic body mass and inverse_mass disagree")
            if not self.local_inertia.is_invertible():
                raise PhysicsValidationError(
                    "dynamic body inertia must be invertible"
                )
        else:
            self.mass = math.inf
            self.inverse_mass = 0.0
            self.local_inertia = Mat3.zero()
            self.local_inverse_inertia = Mat3.zero()

    @classmethod
    def dynamic(
        cls,
        body_id: str,
        shape: CollisionShape,
        *,
        density: float = 1.0,
        position: Vec3 = Vec3(),
        orientation: Quat = Quat(),
        material: PhysicsMaterial = PhysicsMaterial(),
        linear_damping: float = 0.05,
        angular_damping: float = 0.05,
        gravity_scale: float = 1.0,
        continuous: bool = False,
    ) -> "RigidBody":
        props = shape.mass_properties(density)
        if props.center_of_mass != Vec3.zero():
            raise PhysicsValidationError(
                "offset centers of mass require explicit compound-body support"
            )
        inverse_inertia = props.inertia.inverse()
        return cls(
            body_id=body_id,
            shape=shape,
            body_type=BodyType.DYNAMIC,
            position=position,
            orientation=orientation,
            material=material,
            mass=props.mass,
            inverse_mass=1.0 / props.mass,
            local_inertia=props.inertia,
            local_inverse_inertia=inverse_inertia,
            linear_damping=linear_damping,
            angular_damping=angular_damping,
            gravity_scale=gravity_scale,
            continuous=continuous,
        )

    @classmethod
    def static(
        cls,
        body_id: str,
        shape: CollisionShape,
        *,
        position: Vec3 = Vec3(),
        orientation: Quat = Quat(),
        material: PhysicsMaterial = PhysicsMaterial(),
    ) -> "RigidBody":
        return cls(
            body_id=body_id,
            shape=shape,
            body_type=BodyType.STATIC,
            position=position,
            orientation=orientation,
            material=material,
        )

    @classmethod
    def kinematic(
        cls,
        body_id: str,
        shape: CollisionShape,
        *,
        position: Vec3 = Vec3(),
        orientation: Quat = Quat(),
        linear_velocity: Vec3 = Vec3(),
        angular_velocity: Vec3 = Vec3(),
        material: PhysicsMaterial = PhysicsMaterial(),
    ) -> "RigidBody":
        return cls(
            body_id=body_id,
            shape=shape,
            body_type=BodyType.KINEMATIC,
            position=position,
            orientation=orientation,
            linear_velocity=linear_velocity,
            angular_velocity=angular_velocity,
            material=material,
        )

    @property
    def transform(self) -> Transform:
        return Transform(self.position, self.orientation)

    @property
    def movable(self) -> bool:
        return self.body_type is not BodyType.STATIC

    @property
    def dynamic_body(self) -> bool:
        return self.body_type is BodyType.DYNAMIC

    def world_inverse_inertia(self) -> Mat3:
        if not self.dynamic_body:
            return Mat3.zero()
        rotation = self.orientation.to_matrix()
        return rotation.mul_mat(self.local_inverse_inertia).mul_mat(rotation.transpose())

    def velocity_at_world_point(self, point: Vec3) -> Vec3:
        arm = point - self.position
        return self.linear_velocity + self.angular_velocity.cross(arm)

    def wake(self) -> None:
        if self.dynamic_body:
            self.awake = True
            self.sleep_time = 0.0

    def sleep(self) -> None:
        if self.dynamic_body:
            self.awake = False
            self.sleep_time = 0.0
            self.linear_velocity = Vec3.zero()
            self.angular_velocity = Vec3.zero()
            self.clear_accumulators()

    def apply_force(self, force: Vec3, *, point: Vec3 | None = None) -> None:
        if not self.dynamic_body:
            return
        self.force = self.force + force
        if point is not None:
            self.torque = self.torque + (point - self.position).cross(force)
        self.wake()

    def apply_torque(self, torque: Vec3) -> None:
        if not self.dynamic_body:
            return
        self.torque = self.torque + torque
        self.wake()

    def apply_impulse(self, impulse: Vec3, *, point: Vec3 | None = None) -> None:
        if not self.dynamic_body:
            return
        self.linear_velocity = self.linear_velocity + impulse * self.inverse_mass
        if point is not None:
            angular_impulse = (point - self.position).cross(impulse)
            self.angular_velocity = (
                self.angular_velocity + self.world_inverse_inertia().mul_vec(angular_impulse)
            )
        self.wake()

    def apply_angular_impulse(self, angular_impulse: Vec3) -> None:
        if not self.dynamic_body:
            return
        if not isinstance(angular_impulse, Vec3):
            raise PhysicsValidationError("angular_impulse must be Vec3")
        self.angular_velocity = (
            self.angular_velocity
            + self.world_inverse_inertia().mul_vec(angular_impulse)
        )
        self.wake()

    def integrate_forces(self, dt: float, gravity: Vec3) -> None:
        if not self.dynamic_body or not self.awake:
            return
        dt = _non_negative(dt, name="dt")
        acceleration = gravity * self.gravity_scale + self.force * self.inverse_mass
        angular_acceleration = self.world_inverse_inertia().mul_vec(self.torque)
        self.linear_velocity = self.linear_velocity + acceleration * dt
        self.angular_velocity = self.angular_velocity + angular_acceleration * dt
        self.linear_velocity = self.linear_velocity * math.exp(-self.linear_damping * dt)
        self.angular_velocity = self.angular_velocity * math.exp(-self.angular_damping * dt)

    def integrate_orientation(self, dt: float) -> None:
        if not self.movable or (self.dynamic_body and not self.awake):
            return
        dt = _non_negative(dt, name="dt")
        if self.angular_velocity.length_squared() > 0.0:
            self.orientation = self.orientation.integrate_world_angular_velocity(
                self.angular_velocity,
                dt,
            )

    def integrate_velocity(self, dt: float) -> None:
        if not self.movable or (self.dynamic_body and not self.awake):
            return
        dt = _non_negative(dt, name="dt")
        self.position = self.position + self.linear_velocity * dt
        self.integrate_orientation(dt)

    def clear_accumulators(self) -> None:
        self.force = Vec3.zero()
        self.torque = Vec3.zero()

    def kinetic_energy(self) -> float:
        if not self.dynamic_body:
            return 0.0
        linear = 0.5 * self.mass * self.linear_velocity.length_squared()
        rotation = self.orientation.to_matrix()
        world_inertia = rotation.mul_mat(self.local_inertia).mul_mat(rotation.transpose())
        angular = 0.5 * self.angular_velocity.dot(world_inertia.mul_vec(self.angular_velocity))
        return linear + angular

    def state_record(self) -> dict[str, object]:
        return {
            "body_id": self.body_id,
            "type": self.body_type.value,
            "shape": self.shape.kind.value,
            "position": self.position.to_tuple(),
            "orientation": (
                self.orientation.w,
                self.orientation.x,
                self.orientation.y,
                self.orientation.z,
            ),
            "linear_velocity": self.linear_velocity.to_tuple(),
            "angular_velocity": self.angular_velocity.to_tuple(),
            "force": self.force.to_tuple(),
            "torque": self.torque.to_tuple(),
            "linear_damping": self.linear_damping,
            "angular_damping": self.angular_damping,
            "gravity_scale": self.gravity_scale,
            "awake": self.awake,
            "sleep_time": self.sleep_time,
            "continuous": self.continuous,
        }
