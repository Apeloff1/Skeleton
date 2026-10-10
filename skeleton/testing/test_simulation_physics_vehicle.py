"""Deterministic raycast-vehicle dynamics and convex CCD anti-tunneling regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    RaycastVehicle,
    RigidBody,
    Vec3,
    VehicleControl,
    VehicleSettings,
    WheelSettings,
    step_vehicles,
)

CHASSIS_HALF = Vec3(0.9, 0.3, 2.0)
CHASSIS_DENSITY = 250.0  # 1080 kg


def _wheels(**overrides) -> tuple[WheelSettings, ...]:
    layout = ((0.8, 1.4), (-0.8, 1.4), (0.8, -1.4), (-0.8, -1.4))
    return tuple(
        WheelSettings(
            f"w{index}",
            Vec3(x, -0.3, z),
            steerable=z > 0.0,
            driven=z < 0.0,
            handbrake=z < 0.0,
            **overrides,
        )
        for index, (x, z) in enumerate(layout)
    )


def _scene(
    *,
    ccd: bool = True,
    position: Vec3 = Vec3(0.0, 1.0, 0.0),
    velocity: Vec3 = Vec3(),
    wheel_overrides: dict | None = None,
) -> tuple[PhysicsWorld, RaycastVehicle, RigidBody]:
    world = PhysicsWorld(PhysicsSettings(ccd_enabled=ccd))
    world.add_body(RigidBody.static("ground", PlaneShape()))
    chassis = RigidBody.dynamic(
        "car",
        BoxShape(CHASSIS_HALF),
        density=CHASSIS_DENSITY,
        position=position,
        continuous=True,
    )
    chassis.linear_velocity = velocity
    world.add_body(chassis)
    vehicle = RaycastVehicle("car", VehicleSettings(_wheels(**(wheel_overrides or {}))))
    vehicle.validate_stability(world)
    return world, vehicle, chassis


def _drive(world, vehicle, control: VehicleControl, steps: int):
    return step_vehicles(world, ((vehicle, control),), steps=steps)


def _up(chassis: RigidBody) -> Vec3:
    return chassis.orientation.rotate(Vec3(0.0, 1.0, 0.0))


def _script(tick: int) -> VehicleControl:
    if tick < 40:
        return VehicleControl()
    if tick < 100:
        return VehicleControl(throttle=1.0)
    if tick < 150:
        return VehicleControl(throttle=0.6, steer=0.8)
    if tick < 170:
        return VehicleControl(handbrake=True, steer=-0.5)
    return VehicleControl(brake=1.0)


# --------------------------------------------------------------- sanity


def test_parked_vehicle_settles_at_spring_equilibrium_and_sleeps() -> None:
    world, vehicle, chassis = _scene()
    results = _drive(world, vehicle, VehicleControl(), 120)

    wheel = vehicle.settings.wheels[0]
    expected_compression = chassis.mass * 9.81 / (4.0 * wheel.stiffness)
    expected_y = wheel.radius + (wheel.rest_length - expected_compression) + CHASSIS_HALF.y
    assert chassis.position.y == pytest.approx(expected_y, abs=2.0e-3)
    assert chassis.position.x == 0.0 and chassis.position.z == 0.0
    assert not chassis.awake
    assert results[-1][0].asleep
    assert results[-1][0].grounded_wheels == 4

    # An asleep, idle vehicle does no work and stays bit-stable.
    digest = world.state_digest
    position = chassis.position
    _drive(world, vehicle, VehicleControl(), 60)
    assert chassis.position == position
    assert not chassis.awake
    assert world.state_digest != digest  # tick advanced
    assert chassis.linear_velocity == Vec3()


def test_throttle_drives_straight_without_solver_order_yaw() -> None:
    world, vehicle, chassis = _scene()
    _drive(world, vehicle, VehicleControl(), 60)
    speeds = []
    for result in _drive(world, vehicle, VehicleControl(throttle=1.0), 180):
        speeds.append(result[0].forward_speed)

    assert chassis.linear_velocity.z > 15.0
    assert chassis.position.z > 25.0
    # Symmetric (Jacobi) suspension and tire solves: no lateral drift or yaw.
    assert abs(chassis.position.x) < 1.0e-9
    assert abs(chassis.angular_velocity.y) < 1.0e-9
    assert _up(chassis).y > 0.99
    assert all(later >= earlier - 1.0e-9 for earlier, later in zip(speeds, speeds[1:]))
    wheels = vehicle.last_update.wheels
    assert all(row.spin_speed > 0.0 for row in wheels)


def test_reverse_throttle_drives_backward() -> None:
    world, vehicle, chassis = _scene()
    _drive(world, vehicle, VehicleControl(), 30)
    _drive(world, vehicle, VehicleControl(throttle=-1.0), 90)
    assert chassis.linear_velocity.z < -5.0
    assert chassis.position.z < -3.0


def test_brake_stops_without_reversing() -> None:
    world, vehicle, chassis = _scene()
    _drive(world, vehicle, VehicleControl(), 30)
    _drive(world, vehicle, VehicleControl(throttle=1.0), 150)
    start = chassis.linear_velocity.z
    assert start > 15.0

    furthest = chassis.position.z
    stopped_at = None
    for tick in range(360):
        _drive(world, vehicle, VehicleControl(brake=1.0), 1)
        speed = chassis.linear_velocity.z
        assert speed <= start + 1.0e-9
        furthest = max(furthest, chassis.position.z)
        # Brakes stop the contact patches; only suspension rebound (nose-dive
        # pitch rock-back, a few cm) may move the chassis, never sustained
        # reverse travel.
        assert speed > -0.25
        spins = [row.spin_speed for row in vehicle.last_update.wheels]
        assert min(spins) * vehicle.settings.wheels[0].radius > -0.05
        assert chassis.position.z >= furthest - 0.05
        if stopped_at is None and abs(speed) < 0.05:
            stopped_at = tick
    assert stopped_at is not None and stopped_at < 240
    assert not chassis.awake  # held by brakes, then parked
    assert chassis.linear_velocity.length() < 1.0e-6


def test_positive_steer_yaws_left_and_stays_upright() -> None:
    world, vehicle, chassis = _scene()
    _drive(world, vehicle, VehicleControl(), 30)
    _drive(world, vehicle, VehicleControl(throttle=1.0), 90)
    _drive(world, vehicle, VehicleControl(throttle=0.5, steer=1.0), 120)

    assert vehicle.steer_angle == pytest.approx(vehicle.settings.max_steer_angle)
    assert chassis.angular_velocity.y > 0.1
    assert chassis.position.x > 1.0
    assert _up(chassis).y > 0.98
    front = vehicle.last_update.wheels[0]
    rear = vehicle.last_update.wheels[2]
    assert front.steer_angle == vehicle.steer_angle
    assert rear.steer_angle == 0.0


def test_steering_is_rate_limited() -> None:
    world, vehicle, _ = _scene()
    _drive(world, vehicle, VehicleControl(steer=1.0), 1)
    limit = vehicle.settings.steer_rate * world.settings.fixed_dt
    assert vehicle.steer_angle == pytest.approx(limit)


def test_airborne_vehicle_applies_no_wheel_impulses() -> None:
    world, vehicle, chassis = _scene(position=Vec3(0.0, 50.0, 0.0))
    results = _drive(world, vehicle, VehicleControl(throttle=1.0, steer=1.0), 10)
    assert all(result[0].grounded_wheels == 0 for result in results)
    assert chassis.linear_velocity.x == 0.0
    assert chassis.linear_velocity.z == 0.0
    assert chassis.angular_velocity == Vec3()
    expected = -9.81 * 10 * world.settings.fixed_dt
    assert chassis.linear_velocity.y == pytest.approx(expected, rel=0.02)


def test_hard_landing_bump_stop_keeps_chassis_above_ground() -> None:
    world, vehicle, chassis = _scene(position=Vec3(0.0, 6.0, 0.0))
    bottomed = 0
    lowest = math.inf
    for result in _drive(world, vehicle, VehicleControl(), 240):
        bottomed += sum(1 for row in result[0].wheels if row.bottomed_out)
        lowest = min(lowest, chassis.position.y)
    assert bottomed > 0
    # Chassis bottom (y - half height) never reaches the ground plane.
    assert lowest - CHASSIS_HALF.y > 0.0
    assert all(math.isfinite(value) for value in chassis.position.to_tuple())
    assert chassis.position.y == pytest.approx(0.9245, abs=5.0e-3)


# ---------------------------------------------------------- determinism


def _run_script(steps: int) -> tuple[list[str], list[str]]:
    world, vehicle, _ = _scene()
    world_digests: list[str] = []
    vehicle_digests: list[str] = []
    for tick in range(steps):
        _drive(world, vehicle, _script(tick), 1)
        world_digests.append(world.state_digest)
        vehicle_digests.append(vehicle.state_digest)
    return world_digests, vehicle_digests


def test_replay_is_bit_identical_across_independent_worlds() -> None:
    first = _run_script(200)
    second = _run_script(200)
    assert first == second
    assert len(set(first[0])) > 150  # the state is actually evolving


def test_snapshot_and_vehicle_state_restore_replays_exactly() -> None:
    world, vehicle, _ = _scene()
    for tick in range(90):
        _drive(world, vehicle, _script(tick), 1)
    snapshot = world.capture_snapshot()
    state = vehicle.capture_state()

    expected = []
    for tick in range(90, 180):
        _drive(world, vehicle, _script(tick), 1)
        expected.append((world.state_digest, vehicle.state_digest))

    world.restore_snapshot(snapshot)
    vehicle.restore_state(state)
    replayed = []
    for tick in range(90, 180):
        _drive(world, vehicle, _script(tick), 1)
        replayed.append((world.state_digest, vehicle.state_digest))
    assert replayed == expected


def test_vehicle_state_restore_rejects_mismatches() -> None:
    _, vehicle, _ = _scene()
    other = RaycastVehicle(
        "car",
        VehicleSettings(_wheels(), max_drive_force=1.0),
    )
    with pytest.raises(PhysicsValidationError):
        vehicle.restore_state(other.capture_state())
    with pytest.raises(PhysicsValidationError):
        vehicle.restore_state("not-a-state")  # type: ignore[arg-type]


# ------------------------------------------------------ stability / CCD


def test_long_run_stability_bounded_energy_and_sleep() -> None:
    world, vehicle, chassis = _scene()
    peak = 0.0
    for tick in range(240):
        _drive(world, vehicle, _script(tick), 1)
        peak = max(peak, chassis.kinetic_energy())
        assert all(math.isfinite(value) for value in chassis.position.to_tuple())
        assert _up(chassis).y > 0.9
    # Idle after braking: suspension rebound may trade spring and kinetic
    # energy, but kinetic energy stays bounded and the vehicle parks.
    start = chassis.kinetic_energy()
    ceiling = max(start, 50.0)
    for _ in range(360):
        _drive(world, vehicle, VehicleControl(), 1)
        assert chassis.kinetic_energy() <= ceiling
    assert chassis.kinetic_energy() == 0.0
    assert peak > 1.0e4
    assert not chassis.awake
    assert chassis.position.y == pytest.approx(0.9245, abs=5.0e-3)


def test_ccd_prevents_vehicle_tunneling_through_thin_wall() -> None:
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(5.0, 2.0, 0.05)),
        position=Vec3(0.0, 1.0, 9.0),
    )
    # 360 m/s moves the 4 m chassis 6 m per tick: discrete collision skips
    # the 0.1 m wall entirely, continuous collision must stop it.
    world, vehicle, chassis = _scene(velocity=Vec3(0.0, 0.0, 360.0))
    world.add_body(wall)
    furthest = -math.inf
    for _ in range(30):
        _drive(world, vehicle, VehicleControl(throttle=1.0), 1)
        furthest = max(furthest, chassis.position.z)
    assert furthest + CHASSIS_HALF.z <= 9.0 - 0.05 + 1.0e-3

    control_world, control_vehicle, control_chassis = _scene(
        ccd=False,
        velocity=Vec3(0.0, 0.0, 360.0),
    )
    control_world.add_body(
        RigidBody.static(
            "wall",
            BoxShape(Vec3(5.0, 2.0, 0.05)),
            position=Vec3(0.0, 1.0, 9.0),
        )
    )
    _drive(control_world, control_vehicle, VehicleControl(throttle=1.0), 5)
    assert control_chassis.position.z > 20.0  # proves the scenario tunnels without CCD


def test_default_settings_box_ccd_resolves_residual_toi_gap() -> None:
    """Default ccd_contact_slop (1e-7) is tighter than the 1e-6 convex TOI tolerance."""
    world = PhysicsWorld()
    world.add_body(
        RigidBody.static(
            "wall",
            BoxShape(Vec3(5.0, 2.0, 0.05)),
            position=Vec3(0.0, 1.0, 12.0),
        )
    )
    box = RigidBody.dynamic(
        "box",
        BoxShape(CHASSIS_HALF),
        density=CHASSIS_DENSITY,
        position=Vec3(0.0, 1.0, 0.0),
        continuous=True,
        gravity_scale=0.0,
    )
    box.linear_velocity = Vec3(0.0, 0.0, 90.0)
    world.add_body(box)
    receipts = world.step(20)
    assert sum(row.ccd_clamps for row in receipts) >= 1
    assert box.position.z + CHASSIS_HALF.z <= 12.0 - 0.05 + 1.0e-3


# ----------------------------------------------------------- validation


def test_stability_validation_rejects_unstable_suspension() -> None:
    world, _, _ = _scene()
    stiff = RaycastVehicle("car", VehicleSettings(_wheels(stiffness=5.0e6)))
    with pytest.raises(PhysicsValidationError, match="too stiff"):
        stiff.validate_stability(world)
    damped = RaycastVehicle("car", VehicleSettings(_wheels(compression_damping=5.0e5)))
    with pytest.raises(PhysicsValidationError, match="damping"):
        damped.validate_stability(world)


def test_settings_and_controls_validate_inputs() -> None:
    with pytest.raises(PhysicsValidationError):
        VehicleSettings(())
    with pytest.raises(PhysicsValidationError):
        VehicleSettings((WheelSettings("a", Vec3()), WheelSettings("a", Vec3(1.0, 0.0, 0.0))))
    with pytest.raises(PhysicsValidationError):
        WheelSettings("bad id!", Vec3())
    with pytest.raises(PhysicsValidationError):
        WheelSettings("w", Vec3(), radius=0.0)
    with pytest.raises(PhysicsValidationError):
        VehicleSettings(_wheels(), max_steer_angle=2.0)
    with pytest.raises(PhysicsValidationError):
        VehicleControl(throttle=1.5)
    with pytest.raises(PhysicsValidationError):
        VehicleControl(steer=float("nan"))
    with pytest.raises(PhysicsValidationError):
        VehicleControl(brake=-0.1)
    with pytest.raises(PhysicsValidationError):
        VehicleControl(handbrake=1)  # type: ignore[arg-type]


def test_chassis_must_be_dynamic_and_controls_unique() -> None:
    world = PhysicsWorld()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    vehicle = RaycastVehicle("ground", VehicleSettings(_wheels()))
    with pytest.raises(PhysicsValidationError):
        vehicle.update(world, VehicleControl())

    world, vehicle, _ = _scene()
    with pytest.raises(PhysicsValidationError):
        step_vehicles(world, ((vehicle, VehicleControl()), (vehicle, VehicleControl())))
    with pytest.raises(PhysicsValidationError):
        step_vehicles(world, ((vehicle, VehicleControl()),), steps=0)
