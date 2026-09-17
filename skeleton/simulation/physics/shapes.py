"""Analytic collision shapes and physically meaningful mass properties."""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from .errors import PhysicsValidationError
from .math3d import AABB, Mat3, Transform, Vec3


def _positive(value: float, *, name: str, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    lower_ok = value >= 0.0 if allow_zero else value > 0.0
    if not math.isfinite(value) or not lower_ok:
        qualifier = "non-negative" if allow_zero else "positive"
        raise PhysicsValidationError(f"{name} must be finite and {qualifier}")
    return value


class ShapeKind(str, Enum):
    SPHERE = "sphere"
    BOX = "box"
    PLANE = "plane"


@dataclass(frozen=True, slots=True)
class MassProperties:
    mass: float
    center_of_mass: Vec3
    inertia: Mat3

    def __post_init__(self) -> None:
        if not math.isfinite(self.mass) or self.mass <= 0.0:
            raise PhysicsValidationError("mass must be finite and positive")


@runtime_checkable
class CollisionShape(Protocol):
    @property
    def kind(self) -> ShapeKind: ...

    def aabb(self, transform: Transform) -> AABB | None: ...

    def support(self, direction: Vec3, transform: Transform) -> Vec3: ...

    def mass_properties(self, density: float) -> MassProperties: ...


@dataclass(frozen=True, slots=True)
class SphereShape:
    radius: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "radius", _positive(self.radius, name="radius"))

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.SPHERE

    def aabb(self, transform: Transform) -> AABB:
        half = Vec3.one() * self.radius
        return AABB.from_center_half_extents(transform.position, half)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        return transform.position + direction.normalized() * self.radius

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        volume = (4.0 / 3.0) * math.pi * self.radius**3
        mass = density * volume
        inertia = (2.0 / 5.0) * mass * self.radius**2
        return MassProperties(mass, Vec3.zero(), Mat3.diagonal(Vec3.one() * inertia))


@dataclass(frozen=True, slots=True)
class BoxShape:
    half_extents: Vec3

    def __post_init__(self) -> None:
        if self.half_extents.min_component() <= 0.0:
            raise PhysicsValidationError("box half extents must be positive")

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.BOX

    def axes(self, transform: Transform) -> tuple[Vec3, Vec3, Vec3]:
        rotation = transform.rotation.to_matrix()
        return tuple(rotation.column(i) for i in range(3))  # type: ignore[return-value]

    def aabb(self, transform: Transform) -> AABB:
        rotation = transform.rotation.to_matrix()
        hx, hy, hz = self.half_extents.to_tuple()
        world_half = Vec3(
            abs(rotation.m00) * hx + abs(rotation.m01) * hy + abs(rotation.m02) * hz,
            abs(rotation.m10) * hx + abs(rotation.m11) * hy + abs(rotation.m12) * hz,
            abs(rotation.m20) * hx + abs(rotation.m21) * hy + abs(rotation.m22) * hz,
        )
        return AABB.from_center_half_extents(transform.position, world_half)

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        local_direction = transform.inverse_transform_vector(direction)
        point = Vec3(
            self.half_extents.x if local_direction.x >= 0.0 else -self.half_extents.x,
            self.half_extents.y if local_direction.y >= 0.0 else -self.half_extents.y,
            self.half_extents.z if local_direction.z >= 0.0 else -self.half_extents.z,
        )
        return transform.transform_point(point)

    def mass_properties(self, density: float) -> MassProperties:
        density = _positive(density, name="density")
        h = self.half_extents
        volume = 8.0 * h.x * h.y * h.z
        mass = density * volume
        inertia = Vec3(
            (mass / 3.0) * (h.y * h.y + h.z * h.z),
            (mass / 3.0) * (h.x * h.x + h.z * h.z),
            (mass / 3.0) * (h.x * h.x + h.y * h.y),
        )
        return MassProperties(mass, Vec3.zero(), Mat3.diagonal(inertia))


@dataclass(frozen=True, slots=True)
class PlaneShape:
    """Infinite plane using local equation normal · x = offset."""

    normal: Vec3 = Vec3(0.0, 1.0, 0.0)
    offset: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "normal", self.normal.normalized())
        object.__setattr__(self, "offset", _positive(self.offset, name="offset", allow_zero=True))

    @property
    def kind(self) -> ShapeKind:
        return ShapeKind.PLANE

    def world_equation(self, transform: Transform) -> tuple[Vec3, float]:
        normal = transform.transform_vector(self.normal).normalized()
        return normal, self.offset + normal.dot(transform.position)

    def aabb(self, transform: Transform) -> None:
        del transform
        return None

    def support(self, direction: Vec3, transform: Transform) -> Vec3:
        del direction, transform
        raise PhysicsValidationError("an infinite plane has no finite support point")

    def mass_properties(self, density: float) -> MassProperties:
        del density
        raise PhysicsValidationError("an infinite plane cannot have finite mass properties")
