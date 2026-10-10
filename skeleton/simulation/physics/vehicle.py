"""Deterministic raycast vehicle dynamics on top of :class:`PhysicsWorld`.

A :class:`RaycastVehicle` drives one dynamic chassis body with N ray-suspended
wheels.  Every fixed step it:

1. casts one ray per wheel from the chassis hardpoint along chassis-down;
2. solves a spring/damper suspension impulse along the hit normal (never
   pulling), with a hard bump stop that removes closing speed when the
   suspension is fully compressed;
3. solves tire impulses sequentially (Gauss-Seidel, fixed wheel order) in the
   contact plane: drive, brake, rolling resistance, and lateral grip, each
   bounded by the friction circle ``mu * suspension_impulse``;
4. applies the equal and opposite impulse to dynamic ground bodies.

All work is plain IEEE-754 arithmetic in a fixed order, so identical inputs
produce bit-identical world and vehicle digests.  Vehicle state (steering,
wheel spin, settle timer) is snapshot/restorable for rollback netcode.

Chassis-local axes: forward is ``+Z``, up is ``+Y``.  A positive steer input
yaws the steered wheels positively about chassis-up (toward ``+X``).

The vehicle uses impulses rather than force accumulators so an idle, settled
vehicle can fall asleep through the world's normal island sleeping; it then
stays asleep until it is given non-idle control or woken by another body.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace

from ..ecs.canonical import digest
from .body import BodyType, RigidBody
from .errors import PhysicsValidationError
from .math3d import EPSILON, Vec3
from .queries import Ray, RayHit

MAX_VEHICLE_WHEELS = 16
_TAU = 2.0 * math.pi
_WHEEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")

_LOCAL_FORWARD = Vec3(0.0, 0.0, 1.0)
_LOCAL_UP = Vec3(0.0, 1.0, 0.0)


def _finite(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhysicsValidationError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise PhysicsValidationError(f"{name} must be finite")
    return value


def _positive(value: float, *, name: str) -> float:
    value = _finite(value, name=name)
    if value <= 0.0:
        raise PhysicsValidationError(f"{name} must be positive")
    return value


def _non_negative(value: float, *, name: str) -> float:
    value = _finite(value, name=name)
    if value < 0.0:
        raise PhysicsValidationError(f"{name} must be non-negative")
    return value


def _unit_interval(value: float, *, name: str, signed: bool = False) -> float:
    value = _finite(value, name=name)
    lower = -1.0 if signed else 0.0
    if not lower <= value <= 1.0:
        raise PhysicsValidationError(f"{name} must be in [{lower:g}, 1]")
    return value


def _inverse_effective_mass(body: RigidBody, point: Vec3, direction: Vec3) -> float:
    arm = (point - body.position).cross(direction)
    return body.inverse_mass + arm.dot(body.world_inverse_inertia().mul_vec(arm))


@dataclass(frozen=True, slots=True)
class WheelSettings:
    """Static description of one ray-suspended wheel."""

    wheel_id: str
    attachment: Vec3
    radius: float = 0.35
    rest_length: float = 0.35
    stiffness: float = 35_000.0
    compression_damping: float = 4_000.0
    relaxation_damping: float = 3_000.0
    max_suspension_force: float = 60_000.0
    friction: float = 1.1
    lateral_response: float = 0.6
    roll_influence: float = 0.15
    steerable: bool = False
    driven: bool = False
    handbrake: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.wheel_id, str) or not _WHEEL_ID_RE.fullmatch(self.wheel_id):
            raise PhysicsValidationError("invalid wheel_id")
        if not isinstance(self.attachment, Vec3):
            raise PhysicsValidationError("wheel attachment must be Vec3")
        for name in ("steerable", "driven", "handbrake"):
            if not isinstance(getattr(self, name), bool):
                raise PhysicsValidationError(f"{name} must be boolean")
        for name in ("radius", "rest_length", "stiffness", "max_suspension_force"):
            object.__setattr__(self, name, _positive(getattr(self, name), name=name))
        for name in ("compression_damping", "relaxation_damping", "friction"):
            object.__setattr__(self, name, _non_negative(getattr(self, name), name=name))
        object.__setattr__(
            self,
            "lateral_response",
            _unit_interval(self.lateral_response, name="lateral_response"),
        )
        object.__setattr__(
            self,
            "roll_influence",
            _unit_interval(self.roll_influence, name="roll_influence"),
        )

    @property
    def ray_length(self) -> float:
        return self.rest_length + self.radius

    def state_record(self) -> dict[str, object]:
        return {
            "wheel_id": self.wheel_id,
            "attachment": self.attachment.to_tuple(),
            "radius": self.radius,
            "rest_length": self.rest_length,
            "stiffness": self.stiffness,
            "compression_damping": self.compression_damping,
            "relaxation_damping": self.relaxation_damping,
            "max_suspension_force": self.max_suspension_force,
            "friction": self.friction,
            "lateral_response": self.lateral_response,
            "roll_influence": self.roll_influence,
            "steerable": self.steerable,
            "driven": self.driven,
            "handbrake": self.handbrake,
        }


@dataclass(frozen=True, slots=True)
class VehicleSettings:
    """Drivetrain and wheel layout for one :class:`RaycastVehicle`."""

    wheels: tuple[WheelSettings, ...]
    max_steer_angle: float = 0.55
    steer_rate: float = 2.5
    max_drive_force: float = 9_000.0
    max_brake_force: float = 14_000.0
    handbrake_force: float = 9_000.0
    handbrake_grip: float = 0.35
    rolling_resistance: float = 0.015
    idle_brake_force: float = 300.0
    settle_speed: float = 0.05
    settle_after_seconds: float = 0.5

    def __post_init__(self) -> None:
        if not isinstance(self.wheels, tuple) or not self.wheels:
            raise PhysicsValidationError("vehicle requires a non-empty wheel tuple")
        if len(self.wheels) > MAX_VEHICLE_WHEELS:
            raise PhysicsValidationError("vehicle wheel bound exceeded")
        if not all(isinstance(wheel, WheelSettings) for wheel in self.wheels):
            raise PhysicsValidationError("wheels must be WheelSettings")
        ids = [wheel.wheel_id for wheel in self.wheels]
        if len(set(ids)) != len(ids):
            raise PhysicsValidationError("duplicate wheel_id")
        angle = _positive(self.max_steer_angle, name="max_steer_angle")
        if angle >= math.pi * 0.5:
            raise PhysicsValidationError("max_steer_angle must be below pi/2")
        object.__setattr__(self, "max_steer_angle", angle)
        object.__setattr__(self, "steer_rate", _positive(self.steer_rate, name="steer_rate"))
        for name in (
            "max_drive_force",
            "max_brake_force",
            "handbrake_force",
            "rolling_resistance",
            "idle_brake_force",
            "settle_speed",
        ):
            object.__setattr__(self, name, _non_negative(getattr(self, name), name=name))
        object.__setattr__(
            self,
            "handbrake_grip",
            _unit_interval(self.handbrake_grip, name="handbrake_grip"),
        )
        object.__setattr__(
            self,
            "settle_after_seconds",
            _positive(self.settle_after_seconds, name="settle_after_seconds"),
        )

    @property
    def driven_wheels(self) -> int:
        return sum(1 for wheel in self.wheels if wheel.driven)

    @property
    def fingerprint(self) -> str:
        return digest(
            {
                "domain": "skeleton.simulation.physics.vehicle_settings.v1",
                "wheels": [wheel.state_record() for wheel in self.wheels],
                "max_steer_angle": self.max_steer_angle,
                "steer_rate": self.steer_rate,
                "max_drive_force": self.max_drive_force,
                "max_brake_force": self.max_brake_force,
                "handbrake_force": self.handbrake_force,
                "handbrake_grip": self.handbrake_grip,
                "rolling_resistance": self.rolling_resistance,
                "idle_brake_force": self.idle_brake_force,
                "settle_speed": self.settle_speed,
                "settle_after_seconds": self.settle_after_seconds,
            }
        )


@dataclass(frozen=True, slots=True)
class VehicleControl:
    """One tick of driver input. ``throttle < 0`` drives in reverse."""

    throttle: float = 0.0
    brake: float = 0.0
    steer: float = 0.0
    handbrake: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "throttle", _unit_interval(self.throttle, name="throttle", signed=True)
        )
        object.__setattr__(self, "brake", _unit_interval(self.brake, name="brake"))
        object.__setattr__(self, "steer", _unit_interval(self.steer, name="steer", signed=True))
        if not isinstance(self.handbrake, bool):
            raise PhysicsValidationError("handbrake must be boolean")

    @property
    def idle(self) -> bool:
        return self.throttle == 0.0 and self.steer == 0.0


@dataclass(frozen=True, slots=True)
class WheelContact:
    """Per-wheel result of one vehicle update."""

    wheel_id: str
    grounded: bool
    ground_body: str | None
    contact_point: Vec3 | None
    contact_normal: Vec3 | None
    suspension_length: float
    compression: float
    suspension_force: float
    longitudinal_impulse: float
    lateral_impulse: float
    slip_speed: float
    sliding: bool
    bottomed_out: bool
    steer_angle: float
    spin_angle: float
    spin_speed: float
    wheel_center: Vec3


@dataclass(frozen=True, slots=True)
class VehicleUpdateResult:
    tick: int
    asleep: bool
    grounded_wheels: int
    forward_speed: float
    wheels: tuple[WheelContact, ...]


@dataclass(frozen=True, slots=True)
class VehicleState:
    """Rollback-safe vehicle-side state (the chassis lives in the world)."""

    chassis_id: str
    settings_fingerprint: str
    steer_angle: float
    spin_angles: tuple[float, ...]
    spin_speeds: tuple[float, ...]
    settle_time: float
    last_grounded: int
    state_digest: str


class RaycastVehicle:
    """Ray-suspended wheeled vehicle bound to one dynamic chassis body."""

    def __init__(self, chassis_id: str, settings: VehicleSettings) -> None:
        if not isinstance(chassis_id, str) or not chassis_id:
            raise PhysicsValidationError("chassis_id must be a non-empty string")
        if not isinstance(settings, VehicleSettings):
            raise PhysicsValidationError("settings must be VehicleSettings")
        self.chassis_id = chassis_id
        self.settings = settings
        count = len(settings.wheels)
        self._steer_angle = 0.0
        self._spin_angles = [0.0] * count
        self._spin_speeds = [0.0] * count
        self._settle_time = 0.0
        self._last_grounded = 0
        self._last: VehicleUpdateResult | None = None

    # ------------------------------------------------------------------ state
    @property
    def steer_angle(self) -> float:
        return self._steer_angle

    @property
    def last_update(self) -> VehicleUpdateResult | None:
        return self._last

    def _state_payload(self) -> dict[str, object]:
        return {
            "domain": "skeleton.simulation.physics.vehicle_state.v1",
            "chassis_id": self.chassis_id,
            "settings": self.settings.fingerprint,
            "steer_angle": self._steer_angle,
            "spin_angles": tuple(self._spin_angles),
            "spin_speeds": tuple(self._spin_speeds),
            "settle_time": self._settle_time,
            "last_grounded": self._last_grounded,
        }

    @property
    def state_digest(self) -> str:
        return digest(self._state_payload())

    def capture_state(self) -> VehicleState:
        return VehicleState(
            chassis_id=self.chassis_id,
            settings_fingerprint=self.settings.fingerprint,
            steer_angle=self._steer_angle,
            spin_angles=tuple(self._spin_angles),
            spin_speeds=tuple(self._spin_speeds),
            settle_time=self._settle_time,
            last_grounded=self._last_grounded,
            state_digest=self.state_digest,
        )

    def restore_state(self, state: VehicleState) -> None:
        if not isinstance(state, VehicleState):
            raise PhysicsValidationError("restore requires VehicleState")
        if state.chassis_id != self.chassis_id:
            raise PhysicsValidationError("vehicle state chassis mismatch")
        if state.settings_fingerprint != self.settings.fingerprint:
            raise PhysicsValidationError("vehicle state settings mismatch")
        count = len(self.settings.wheels)
        if len(state.spin_angles) != count or len(state.spin_speeds) != count:
            raise PhysicsValidationError("vehicle state wheel count mismatch")
        previous = self.capture_state()
        self._steer_angle = state.steer_angle
        self._spin_angles = list(state.spin_angles)
        self._spin_speeds = list(state.spin_speeds)
        self._settle_time = state.settle_time
        self._last_grounded = state.last_grounded
        if self.state_digest != state.state_digest:
            self._steer_angle = previous.steer_angle
            self._spin_angles = list(previous.spin_angles)
            self._spin_speeds = list(previous.spin_speeds)
            self._settle_time = previous.settle_time
            self._last_grounded = previous.last_grounded
            raise PhysicsValidationError("vehicle state digest mismatch")

    # ------------------------------------------------------------- validation
    def _chassis(self, world: object) -> RigidBody:
        chassis = world.get_body(self.chassis_id)  # type: ignore[attr-defined]
        if chassis.body_type is not BodyType.DYNAMIC:
            raise PhysicsValidationError("vehicle chassis must be a dynamic body")
        return chassis

    def validate_stability(self, world: object) -> None:
        """Reject suspension tunings that the fixed step cannot integrate.

        The suspension is integrated semi-implicitly at ``world.settings.fixed_dt``.
        With the chassis mass shared evenly across wheels, a spring is stable
        when ``dt * sqrt(k / m_wheel) < 2``; we require a 2x margin, and the
        damper must not remove more than the full relative speed in one step.
        """
        chassis = self._chassis(world)
        dt = world.settings.fixed_dt  # type: ignore[attr-defined]
        wheel_mass = chassis.mass / len(self.settings.wheels)
        for wheel in self.settings.wheels:
            if dt * math.sqrt(wheel.stiffness / wheel_mass) >= 1.0:
                raise PhysicsValidationError(
                    f"wheel {wheel.wheel_id} suspension too stiff for fixed_dt"
                )
            damping = max(wheel.compression_damping, wheel.relaxation_damping)
            if damping * dt / wheel_mass >= 1.0:
                raise PhysicsValidationError(
                    f"wheel {wheel.wheel_id} suspension damping too high for fixed_dt"
                )

    # ----------------------------------------------------------------- update
    def _advance_steering(self, target: float, dt: float) -> None:
        delta = target - self._steer_angle
        limit = self.settings.steer_rate * dt
        if delta > limit:
            delta = limit
        elif delta < -limit:
            delta = -limit
        self._steer_angle += delta

    def update(self, world: object, control: VehicleControl) -> VehicleUpdateResult:
        """Apply this tick's suspension and tire impulses to the chassis.

        Call once per fixed step before ``world.step(1)`` (or use
        :func:`step_vehicles`).
        """
        if not isinstance(control, VehicleControl):
            raise PhysicsValidationError("control must be VehicleControl")
        chassis = self._chassis(world)
        settings = self.settings
        dt = world.settings.fixed_dt  # type: ignore[attr-defined]
        tick = world.tick  # type: ignore[attr-defined]

        self._advance_steering(control.steer * settings.max_steer_angle, dt)

        # Respect island sleeping: an asleep chassis with idle input does no
        # work, so a parked vehicle costs nothing and stays bit-stable.
        if chassis.awake:
            self._update_settle(chassis, control, dt)
        if not chassis.awake and control.idle:
            wheels = tuple(
                self._idle_contact(index, chassis) for index in range(len(settings.wheels))
            )
            self._last = VehicleUpdateResult(
                tick=tick,
                asleep=True,
                grounded_wheels=sum(1 for row in wheels if row.grounded),
                forward_speed=0.0,
                wheels=wheels,
            )
            return self._last
        if not control.idle:
            chassis.wake()

        rotation = chassis.orientation
        up = rotation.rotate(_LOCAL_UP).normalized()
        down = -up
        body_forward = rotation.rotate(_LOCAL_FORWARD).normalized()
        driven = settings.driven_wheels
        drive_per_wheel = (
            control.throttle * settings.max_drive_force / driven if driven else 0.0
        )

        # Phase 1: rays and suspension (fixed wheel order).
        probes: list[tuple[WheelSettings, Vec3, RayHit | None]] = []
        for wheel in settings.wheels:
            hardpoint = chassis.transform.transform_point(wheel.attachment)
            hit = world.raycast_closest(  # type: ignore[attr-defined]
                Ray(hardpoint, down, wheel.ray_length),
                ignore=(self.chassis_id,),
            )
            probes.append((wheel, hardpoint, hit))

        contacts: list[WheelContact] = []
        suspension_impulses: list[float] = []
        struts: list[tuple[int, Vec3, Vec3, RigidBody, float, float, bool]] = []
        grounded = 0
        for index, (wheel, hardpoint, hit) in enumerate(probes):
            steer = self._steer_angle if wheel.steerable else 0.0
            if hit is None or hit.normal.dot(up) <= EPSILON:
                suspension_impulses.append(0.0)
                self._spin_speeds[index] *= math.exp(-0.5 * dt)
                self._spin_angles[index] = math.fmod(
                    self._spin_angles[index] + self._spin_speeds[index] * dt, _TAU
                )
                contacts.append(
                    WheelContact(
                        wheel_id=wheel.wheel_id,
                        grounded=False,
                        ground_body=None,
                        contact_point=None,
                        contact_normal=None,
                        suspension_length=wheel.rest_length,
                        compression=0.0,
                        suspension_force=0.0,
                        longitudinal_impulse=0.0,
                        lateral_impulse=0.0,
                        slip_speed=0.0,
                        sliding=False,
                        bottomed_out=False,
                        steer_angle=steer,
                        spin_angle=self._spin_angles[index],
                        spin_speed=self._spin_speeds[index],
                        wheel_center=hardpoint + down * wheel.rest_length,
                    )
                )
                continue

            grounded += 1
            normal = hit.normal
            ground = world.get_body(hit.body_id)  # type: ignore[attr-defined]
            length = hit.distance - wheel.radius
            bottomed = length <= 0.0
            length = min(max(length, 0.0), wheel.rest_length)
            compression = wheel.rest_length - length
            point = hit.point
            relative = chassis.velocity_at_world_point(point) - ground.velocity_at_world_point(
                point
            )
            normal_speed = relative.dot(normal)
            damping = (
                wheel.compression_damping if normal_speed < 0.0 else wheel.relaxation_damping
            )
            force = wheel.stiffness * compression - damping * normal_speed
            force = min(max(force, 0.0), wheel.max_suspension_force)
            impulse = force * dt
            inv_normal = _inverse_effective_mass(chassis, point, normal)
            struts.append((index, point, normal, ground, normal_speed, inv_normal, bottomed))
            suspension_impulses.append(impulse)
            contacts.append(
                WheelContact(
                    wheel_id=wheel.wheel_id,
                    grounded=True,
                    ground_body=hit.body_id,
                    contact_point=point,
                    contact_normal=normal,
                    suspension_length=length,
                    compression=compression,
                    suspension_force=impulse / dt,
                    longitudinal_impulse=0.0,
                    lateral_impulse=0.0,
                    slip_speed=0.0,
                    sliding=False,
                    bottomed_out=bottomed,
                    steer_angle=steer,
                    spin_angle=self._spin_angles[index],
                    spin_speed=self._spin_speeds[index],
                    wheel_center=hardpoint + down * length,
                )
            )

        # Suspension impulses are evaluated from one velocity snapshot and
        # applied together, so wheel order cannot bias pitch/roll.
        bottomed_count = sum(1 for strut in struts if strut[6])
        for index, point, normal, ground, normal_speed, inv_normal, bottomed in struts:
            impulse = suspension_impulses[index]
            if bottomed and inv_normal > EPSILON:
                # Bump stop: a fully compressed strut behaves like a contact and
                # removes its share of the remaining closing speed, so hard
                # landings cannot push the chassis through the ground.
                closing = normal_speed + impulse * inv_normal
                if closing < 0.0:
                    impulse += -closing / inv_normal / bottomed_count
                    suspension_impulses[index] = impulse
                    contacts[index] = replace(contacts[index], suspension_force=impulse / dt)
        for index, point, normal, ground, _speed, _inv, _bottomed in struts:
            impulse = suspension_impulses[index]
            if impulse > 0.0:
                chassis.apply_impulse(normal * impulse, point=point)
                if ground.body_type is BodyType.DYNAMIC:
                    ground.apply_impulse(-(normal * impulse), point=point)

        # Phase 2: tires. Impulses are computed from one shared velocity
        # snapshot (Jacobi) and split across grounded wheels, then applied in
        # fixed wheel order. Unlike sequential solving this is symmetric, so a
        # straight-line launch does not develop a solver-order yaw bias.
        planned: list[tuple[int, Vec3, Vec3, Vec3, float, float, float, bool, RigidBody]] = []
        share = 1.0 / grounded if grounded else 0.0
        for index, (wheel, _hardpoint, hit) in enumerate(probes):
            contact = contacts[index]
            if not contact.grounded or hit is None:
                continue
            normal = hit.normal
            point = hit.point
            ground = world.get_body(hit.body_id)  # type: ignore[attr-defined]
            steer = contact.steer_angle
            heading = body_forward
            if steer != 0.0:
                heading = (
                    body_forward * math.cos(steer) + up.cross(body_forward) * math.sin(steer)
                )
            forward = heading - normal * heading.dot(normal)
            forward = forward.normalized(fallback=body_forward)
            lateral = normal.cross(forward).normalized(fallback=up.cross(forward))

            relative = chassis.velocity_at_world_point(point) - ground.velocity_at_world_point(
                point
            )
            long_speed = relative.dot(forward)
            lat_speed = relative.dot(lateral)
            inv_long = _inverse_effective_mass(chassis, point, forward)
            inv_lat = _inverse_effective_mass(chassis, point, lateral)
            handbraking = control.handbrake and wheel.handbrake
            grip = settings.handbrake_grip if handbraking else 1.0

            # Longitudinal: drive, then resistive impulses that may stop but
            # never reverse the wheel's share of ground speed.
            long_impulse = drive_per_wheel * dt if wheel.driven else 0.0
            resist = control.brake * settings.max_brake_force / len(settings.wheels)
            if handbraking:
                resist += settings.handbrake_force
            if control.throttle == 0.0:
                resist += settings.idle_brake_force / len(settings.wheels)
            resist = resist * dt + settings.rolling_resistance * suspension_impulses[index]
            if inv_long > EPSILON and resist > 0.0:
                speed_after_drive = long_speed + long_impulse * inv_long * share
                stop = -speed_after_drive / inv_long * share
                long_impulse += max(-resist, min(resist, stop))

            lat_impulse = 0.0
            if inv_lat > EPSILON:
                lat_impulse = -lat_speed / inv_lat * wheel.lateral_response * share

            limit = wheel.friction * suspension_impulses[index] * grip
            magnitude = math.hypot(long_impulse, lat_impulse)
            sliding = False
            if magnitude > limit:
                sliding = True
                scale = limit / magnitude if magnitude > 0.0 else 0.0
                long_impulse *= scale
                lat_impulse *= scale
            planned.append(
                (
                    index,
                    point,
                    forward,
                    lateral,
                    long_impulse,
                    lat_impulse,
                    abs(lat_speed),
                    sliding,
                    ground,
                )
            )

        for index, point, forward, lateral, long_impulse, lat_impulse, slip, sliding, ground in (
            planned
        ):
            wheel = settings.wheels[index]
            if long_impulse != 0.0:
                chassis.apply_impulse(forward * long_impulse, point=point)
                if ground.body_type is BodyType.DYNAMIC:
                    ground.apply_impulse(-(forward * long_impulse), point=point)
            if lat_impulse != 0.0:
                height = (chassis.position - point).dot(up)
                roll_point = point + up * (height * (1.0 - wheel.roll_influence))
                chassis.apply_impulse(lateral * lat_impulse, point=roll_point)
                if ground.body_type is BodyType.DYNAMIC:
                    ground.apply_impulse(-(lateral * lat_impulse), point=point)

        for index, point, forward, _lateral, long_impulse, lat_impulse, slip, sliding, ground in (
            planned
        ):
            wheel = settings.wheels[index]
            contact = contacts[index]
            if control.handbrake and wheel.handbrake:
                spin = 0.0
            else:
                rolled = (
                    chassis.velocity_at_world_point(point)
                    - ground.velocity_at_world_point(point)
                ).dot(forward)
                spin = rolled / wheel.radius
            self._spin_speeds[index] = spin
            self._spin_angles[index] = math.fmod(self._spin_angles[index] + spin * dt, _TAU)
            contacts[index] = WheelContact(
                wheel_id=contact.wheel_id,
                grounded=True,
                ground_body=contact.ground_body,
                contact_point=contact.contact_point,
                contact_normal=contact.contact_normal,
                suspension_length=contact.suspension_length,
                compression=contact.compression,
                suspension_force=contact.suspension_force,
                longitudinal_impulse=long_impulse,
                lateral_impulse=lat_impulse,
                slip_speed=slip,
                sliding=sliding,
                bottomed_out=contact.bottomed_out,
                steer_angle=contact.steer_angle,
                spin_angle=self._spin_angles[index],
                spin_speed=spin,
                wheel_center=contact.wheel_center,
            )

        forward_speed = chassis.linear_velocity.dot(body_forward)
        self._last_grounded = grounded
        self._last = VehicleUpdateResult(
            tick=tick,
            asleep=not chassis.awake,
            grounded_wheels=grounded,
            forward_speed=forward_speed,
            wheels=tuple(contacts),
        )
        return self._last

    def _idle_contact(self, index: int, chassis: RigidBody) -> WheelContact:
        wheel = self.settings.wheels[index]
        previous = self._last.wheels[index] if self._last is not None else None
        hardpoint = chassis.transform.transform_point(wheel.attachment)
        down = -chassis.orientation.rotate(_LOCAL_UP).normalized()
        length = previous.suspension_length if previous is not None else wheel.rest_length
        return WheelContact(
            wheel_id=wheel.wheel_id,
            grounded=previous.grounded if previous is not None else False,
            ground_body=previous.ground_body if previous is not None else None,
            contact_point=previous.contact_point if previous is not None else None,
            contact_normal=previous.contact_normal if previous is not None else None,
            suspension_length=length,
            compression=wheel.rest_length - length,
            suspension_force=0.0,
            longitudinal_impulse=0.0,
            lateral_impulse=0.0,
            slip_speed=0.0,
            sliding=False,
            bottomed_out=False,
            steer_angle=self._steer_angle if wheel.steerable else 0.0,
            spin_angle=self._spin_angles[index],
            spin_speed=0.0,
            wheel_center=hardpoint + down * length,
        )

    def _update_settle(
        self,
        chassis: RigidBody,
        control: VehicleControl,
        dt: float,
    ) -> None:
        """Park an idle, fully grounded, quiet vehicle.

        Runs before this tick's impulses, so velocities are the post-step
        values of the previous tick (near zero at rest).
        """
        limit = self.settings.settle_speed
        quiet = (
            control.idle
            and self._last_grounded == len(self.settings.wheels)
            and chassis.linear_velocity.length() <= limit
            and chassis.angular_velocity.length() <= limit
        )
        if not quiet:
            self._settle_time = 0.0
            return
        self._settle_time += dt
        if self._settle_time >= self.settings.settle_after_seconds:
            self._settle_time = 0.0
            chassis.sleep()
            for index in range(len(self._spin_speeds)):
                self._spin_speeds[index] = 0.0


def step_vehicles(
    world: object,
    controls: tuple[tuple[RaycastVehicle, VehicleControl], ...],
    *,
    steps: int = 1,
) -> tuple[tuple[VehicleUpdateResult, ...], ...]:
    """Advance ``world`` by ``steps`` fixed ticks, updating each vehicle first.

    Vehicles update in the given order every tick, which keeps replays exact.
    Returns one tuple of vehicle results per tick.
    """
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 1:
        raise PhysicsValidationError("steps must be a positive integer")
    pairs = tuple(controls)
    seen: set[str] = set()
    for vehicle, control in pairs:
        if not isinstance(vehicle, RaycastVehicle):
            raise PhysicsValidationError("controls must pair RaycastVehicle with control")
        if not isinstance(control, VehicleControl):
            raise PhysicsValidationError("controls must pair RaycastVehicle with control")
        if vehicle.chassis_id in seen:
            raise PhysicsValidationError("duplicate vehicle chassis in controls")
        seen.add(vehicle.chassis_id)
    output: list[tuple[VehicleUpdateResult, ...]] = []
    for _ in range(steps):
        results = tuple(vehicle.update(world, control) for vehicle, control in pairs)
        world.step(1)  # type: ignore[attr-defined]
        output.append(results)
    return tuple(output)


__all__ = [
    "MAX_VEHICLE_WHEELS",
    "RaycastVehicle",
    "VehicleControl",
    "VehicleSettings",
    "VehicleState",
    "VehicleUpdateResult",
    "WheelContact",
    "WheelSettings",
    "step_vehicles",
]
