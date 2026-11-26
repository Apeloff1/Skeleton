"""Dynamic spheres and kinematic terrain boxes.

Boxes are axis-aligned. Moving terrain changes ``center`` and ``velocity``.
Deformable terrain changes ``half_extents``. Both are read when the step
builds AABBs, so a stale bound cannot survive into the broadphase.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from skeleton.frontier_contact.errors import ContactRejected

_SPEED_LIMIT = 10_000.0
_COMPONENT_LIMIT = 1e8


def _real(value: object, label: str, *, limit: float = _COMPONENT_LIMIT) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContactRejected(f"{label} must be a real number")
    number = float(value)
    if math.isnan(number):
        raise ContactRejected("NaN")
    if not math.isfinite(number) or abs(number) > limit:
        raise ContactRejected(f"{label} out of range")
    return number


def _vector(value: object, label: str) -> tuple[float, float, float]:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ContactRejected(f"{label} must be a 3-vector")
    return (_real(value[0], label), _real(value[1], label), _real(value[2], label))


def _unit_axis(value: object, label: str) -> tuple[float, float, float]:
    axis = _vector(value, label)
    length = math.sqrt(axis[0] * axis[0] + axis[1] * axis[1] + axis[2] * axis[2])
    if not 1.0 - 1e-6 <= length <= 1.0 + 1e-6:
        raise ContactRejected(f"{label} must be a unit bone axis")
    return axis


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ContactRejected(f"{label} is required")
    return value


def _range(value: object, label: str, lo: float, hi: float) -> float:
    number = _real(value, label, limit=max(abs(lo), abs(hi), 1.0))
    if number < lo or number > hi:
        raise ContactRejected(f"{label} out of range")
    return number


@dataclass(frozen=True)
class AABB:
    """Inclusive axis-aligned bound in metres."""

    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]

    def __post_init__(self) -> None:
        low = _vector(self.minimum, "aabb minimum")
        high = _vector(self.maximum, "aabb maximum")
        if any(low[axis] > high[axis] for axis in range(3)):
            raise ContactRejected("aabb minimum exceeds maximum")
        object.__setattr__(self, "minimum", low)
        object.__setattr__(self, "maximum", high)


@dataclass(frozen=True)
class SphereBody:
    """Dynamic sphere. Mass is positive. Spin uses the solid-sphere inertia."""

    body_id: str
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    mass_kg: float
    radius_m: float
    restitution: float = 0.15
    friction: float = 0.6
    angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_id", _identifier(self.body_id, "body id"))
        object.__setattr__(self, "position", _vector(self.position, "position"))
        object.__setattr__(self, "velocity", _vector(self.velocity, "velocity"))
        object.__setattr__(
            self, "angular_velocity", _vector(self.angular_velocity, "angular velocity")
        )
        mass = _real(self.mass_kg, "mass", limit=1_000_000.0)
        if mass < 0.0:
            raise ContactRejected("negative mass")
        if not 0.001 <= mass <= 1_000_000.0:
            raise ContactRejected("mass out of range")
        object.__setattr__(self, "mass_kg", mass)
        object.__setattr__(
            self, "radius_m", _range(self.radius_m, "radius", 0.001, 1000.0)
        )
        object.__setattr__(
            self, "restitution", _range(self.restitution, "restitution", 0.0, 1.0)
        )
        object.__setattr__(
            self, "friction", _range(self.friction, "friction", 0.0, 3.0)
        )
        _reject_speed(self.velocity, "speed")
        _reject_speed(self.angular_velocity, "spin")

    @property
    def inertia_kg_m2(self) -> float:
        """Solid-sphere inertia about the center, ``0.4 m r^2``."""
        return 0.4 * self.mass_kg * self.radius_m * self.radius_m


@dataclass(frozen=True)
class BoxBody:
    """Kinematic or static terrain. Mass must be zero; motion is prescribed."""

    body_id: str
    center: tuple[float, float, float]
    half_extents: tuple[float, float, float]
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    mass_kg: float = 0.0
    restitution: float = 0.2
    friction: float = 0.7

    def __post_init__(self) -> None:
        object.__setattr__(self, "body_id", _identifier(self.body_id, "body id"))
        object.__setattr__(self, "center", _vector(self.center, "center"))
        extents = _vector(self.half_extents, "half extents")
        if any(axis <= 0.0 or axis > 1_000_000.0 for axis in extents):
            raise ContactRejected("half extents out of range")
        object.__setattr__(self, "half_extents", extents)
        object.__setattr__(self, "velocity", _vector(self.velocity, "velocity"))
        mass = _real(self.mass_kg, "mass", limit=1_000_000.0)
        if mass < 0.0:
            raise ContactRejected("negative mass")
        if mass != 0.0:
            raise ContactRejected("kinematic terrain requires zero mass")
        object.__setattr__(self, "mass_kg", mass)
        object.__setattr__(
            self, "restitution", _range(self.restitution, "restitution", 0.0, 1.0)
        )
        object.__setattr__(
            self, "friction", _range(self.friction, "friction", 0.0, 3.0)
        )
        _reject_speed(self.velocity, "speed")


def _reject_speed(velocity: tuple[float, float, float], label: str) -> None:
    speed = math.sqrt(
        velocity[0] * velocity[0]
        + velocity[1] * velocity[1]
        + velocity[2] * velocity[2]
    )
    if speed > _SPEED_LIMIT:
        raise ContactRejected(f"{label} bound exceeded")


def move_box(
    box: BoxBody,
    center: tuple[float, float, float],
    velocity: tuple[float, float, float] | None = None,
) -> BoxBody:
    """Return terrain translated to ``center`` before the next bounds query."""
    if not isinstance(box, BoxBody):
        raise ContactRejected("box required")
    return replace(
        box, center=center, velocity=box.velocity if velocity is None else velocity
    )


def deform_box(box: BoxBody, half_extents: tuple[float, float, float]) -> BoxBody:
    """Return terrain with updated half extents before the next bounds query."""
    if not isinstance(box, BoxBody):
        raise ContactRejected("box required")
    return replace(box, half_extents=half_extents)
