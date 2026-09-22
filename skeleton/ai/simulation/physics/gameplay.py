"""Designer-facing physics calculations built on SI-consistent mechanics.

This layer translates common game-design questions into explicit calculations
instead of hard-coded magic numbers: jump height/apex time, projectile arcs,
fall timing, impact speed, stopping distance, turning radius, and impulses.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .errors import PhysicsValidationError
from .math3d import EPSILON, Vec3


def _positive(value: float, *, name: str, allow_zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    valid = value >= 0.0 if allow_zero else value > 0.0
    if not math.isfinite(value) or not valid:
        raise PhysicsValidationError(f"invalid {name}")
    return value


@dataclass(frozen=True, slots=True)
class GameplayScale:
    """Maps engine distance units to meters while keeping time in seconds."""

    meters_per_unit: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "meters_per_unit",
            _positive(self.meters_per_unit, name="meters_per_unit"),
        )

    def to_meters(self, units: float) -> float:
        return float(units) * self.meters_per_unit

    def from_meters(self, meters: float) -> float:
        return float(meters) / self.meters_per_unit

    def acceleration_to_units(self, meters_per_second_squared: float) -> float:
        return float(meters_per_second_squared) / self.meters_per_unit

    def speed_to_units(self, meters_per_second: float) -> float:
        return float(meters_per_second) / self.meters_per_unit


@dataclass(frozen=True, slots=True)
class JumpTuning:
    jump_height: float
    time_to_apex: float
    gravity: float
    launch_speed: float

    @classmethod
    def from_height_and_apex_time(
        cls,
        jump_height: float,
        time_to_apex: float,
    ) -> "JumpTuning":
        height = _positive(jump_height, name="jump_height")
        apex = _positive(time_to_apex, name="time_to_apex")
        gravity = 2.0 * height / (apex * apex)
        launch_speed = gravity * apex
        return cls(height, apex, gravity, launch_speed)

    @classmethod
    def from_height_and_gravity(cls, jump_height: float, gravity: float) -> "JumpTuning":
        height = _positive(jump_height, name="jump_height")
        gravity = _positive(gravity, name="gravity")
        launch_speed = math.sqrt(2.0 * gravity * height)
        apex = launch_speed / gravity
        return cls(height, apex, gravity, launch_speed)


@dataclass(frozen=True, slots=True)
class ProjectileSolution:
    launch_velocity: Vec3
    flight_time: float
    elevation_radians: float
    arc: str


@dataclass(frozen=True, slots=True)
class GamePhysicsProfile:
    name: str = "earth"
    gravity: Vec3 = Vec3(0.0, -9.81, 0.0)
    scale: GameplayScale = GameplayScale()
    air_density: float = 1.225

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise PhysicsValidationError("profile name must be non-empty")
        if self.gravity.length_squared() <= EPSILON * EPSILON:
            raise PhysicsValidationError("game physics profile requires non-zero gravity")
        object.__setattr__(
            self,
            "air_density",
            _positive(self.air_density, name="air_density", allow_zero=True),
        )

    @classmethod
    def earth(cls, *, meters_per_unit: float = 1.0) -> "GamePhysicsProfile":
        return cls(scale=GameplayScale(meters_per_unit))

    @classmethod
    def moon(cls, *, meters_per_unit: float = 1.0) -> "GamePhysicsProfile":
        return cls(
            name="moon",
            gravity=Vec3(0.0, -1.62, 0.0),
            scale=GameplayScale(meters_per_unit),
        )

    @property
    def gravity_magnitude(self) -> float:
        return self.gravity.length()

    @property
    def up(self) -> Vec3:
        return (-self.gravity).normalized()

    def jump_for_height(self, height_units: float) -> JumpTuning:
        height_meters = self.scale.to_meters(_positive(height_units, name="height_units"))
        tuning = JumpTuning.from_height_and_gravity(height_meters, self.gravity_magnitude)
        return JumpTuning(
            jump_height=height_units,
            time_to_apex=tuning.time_to_apex,
            gravity=self.scale.acceleration_to_units(tuning.gravity),
            launch_speed=self.scale.speed_to_units(tuning.launch_speed),
        )

    def time_to_fall(self, height_units: float, *, initial_down_speed: float = 0.0) -> float:
        height = self.scale.to_meters(_positive(height_units, name="height_units"))
        initial = self.scale.to_meters(
            _positive(initial_down_speed, name="initial_down_speed", allow_zero=True)
        )
        gravity = self.gravity_magnitude
        # h = v0*t + 1/2*g*t^2; choose the non-negative root.
        return (-initial + math.sqrt(initial * initial + 2.0 * gravity * height)) / gravity

    def impact_speed(self, height_units: float, *, initial_down_speed: float = 0.0) -> float:
        height = self.scale.to_meters(_positive(height_units, name="height_units"))
        initial = self.scale.to_meters(
            _positive(initial_down_speed, name="initial_down_speed", allow_zero=True)
        )
        speed = math.sqrt(initial * initial + 2.0 * self.gravity_magnitude * height)
        return self.scale.speed_to_units(speed)

    @staticmethod
    def stopping_distance(speed: float, deceleration: float) -> float:
        speed = _positive(speed, name="speed", allow_zero=True)
        deceleration = _positive(deceleration, name="deceleration")
        return speed * speed / (2.0 * deceleration)

    @staticmethod
    def stopping_time(speed: float, deceleration: float) -> float:
        speed = _positive(speed, name="speed", allow_zero=True)
        deceleration = _positive(deceleration, name="deceleration")
        return speed / deceleration

    @staticmethod
    def turning_radius(speed: float, lateral_acceleration: float) -> float:
        speed = _positive(speed, name="speed", allow_zero=True)
        lateral = _positive(lateral_acceleration, name="lateral_acceleration")
        return speed * speed / lateral

    @staticmethod
    def impulse_for_delta_velocity(mass: float, delta_velocity: Vec3) -> Vec3:
        mass = _positive(mass, name="mass")
        return delta_velocity * mass

    @staticmethod
    def kinetic_energy(mass: float, speed: float) -> float:
        mass = _positive(mass, name="mass")
        speed = _positive(speed, name="speed", allow_zero=True)
        return 0.5 * mass * speed * speed

    def terminal_velocity(
        self,
        *,
        mass: float,
        drag_coefficient: float,
        reference_area: float,
    ) -> float:
        mass = _positive(mass, name="mass")
        coefficient = _positive(drag_coefficient, name="drag_coefficient")
        area = _positive(reference_area, name="reference_area")
        if self.air_density <= 0.0:
            return math.inf
        speed_mps = math.sqrt(
            (2.0 * mass * self.gravity_magnitude)
            / (self.air_density * coefficient * area)
        )
        return self.scale.speed_to_units(speed_mps)

    def projectile_solutions(
        self,
        origin: Vec3,
        target: Vec3,
        speed_units_per_second: float,
    ) -> tuple[ProjectileSolution, ...]:
        """Solve low/high ballistic arcs under uniform gravity.

        The derivation works in the local gravity frame, so gravity need not be
        aligned with world Y.  Targets with no real ballistic solution return an
        empty tuple rather than a fabricated trajectory.
        """

        speed_units = _positive(speed_units_per_second, name="speed_units_per_second")
        speed = self.scale.to_meters(speed_units)
        displacement_units = target - origin
        displacement = displacement_units * self.scale.meters_per_unit
        up = self.up
        vertical = displacement.dot(up)
        horizontal_vector = displacement - up * vertical
        horizontal = horizontal_vector.length()
        gravity = self.gravity_magnitude

        if horizontal <= EPSILON:
            if vertical <= 0.0:
                direction = -up
                drop = -vertical
                time = (-speed + math.sqrt(speed * speed + 2.0 * gravity * drop)) / gravity
                return (
                    ProjectileSolution(
                        launch_velocity=direction * speed_units,
                        flight_time=time,
                        elevation_radians=-math.pi * 0.5,
                        arc="vertical",
                    ),
                )
            discriminant = speed * speed - 2.0 * gravity * vertical
            if discriminant < 0.0:
                return ()
            time = (speed - math.sqrt(max(0.0, discriminant))) / gravity
            return (
                ProjectileSolution(
                    launch_velocity=up * speed_units,
                    flight_time=time,
                    elevation_radians=math.pi * 0.5,
                    arc="vertical",
                ),
            )

        speed_sq = speed * speed
        discriminant = speed_sq * speed_sq - gravity * (
            gravity * horizontal * horizontal + 2.0 * vertical * speed_sq
        )
        if discriminant < 0.0:
            return ()

        horizontal_direction = horizontal_vector / horizontal
        root = math.sqrt(max(0.0, discriminant))
        tan_values = (
            ("low", (speed_sq - root) / (gravity * horizontal)),
            ("high", (speed_sq + root) / (gravity * horizontal)),
        )
        solutions: list[ProjectileSolution] = []
        for arc, tangent in tan_values:
            angle = math.atan(tangent)
            cosine = math.cos(angle)
            if abs(cosine) <= EPSILON:
                continue
            velocity_mps = (
                horizontal_direction * (speed * cosine)
                + up * (speed * math.sin(angle))
            )
            flight_time = horizontal / (speed * cosine)
            solutions.append(
                ProjectileSolution(
                    launch_velocity=velocity_mps / self.scale.meters_per_unit,
                    flight_time=flight_time,
                    elevation_radians=angle,
                    arc=arc,
                )
            )

        if len(solutions) == 2 and abs(
            solutions[0].elevation_radians - solutions[1].elevation_radians
        ) <= 1.0e-10:
            return (solutions[0],)
        return tuple(solutions)

    def projectile_position(
        self,
        origin: Vec3,
        launch_velocity_units: Vec3,
        time_seconds: float,
    ) -> Vec3:
        time_seconds = _positive(time_seconds, name="time_seconds", allow_zero=True)
        velocity_mps = launch_velocity_units * self.scale.meters_per_unit
        displacement_meters = (
            velocity_mps * time_seconds
            + self.gravity * (0.5 * time_seconds * time_seconds)
        )
        return origin + displacement_meters / self.scale.meters_per_unit
