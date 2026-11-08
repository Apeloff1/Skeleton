"""Adversarial vehicle rollback snapshot integrity and bounded stepping."""
from __future__ import annotations
from dataclasses import replace
import math
import pytest
from skeleton.simulation.physics.vehicle import VehicleControl, WheelSettings, VehicleSettings, RaycastVehicle, step_vehicles
from skeleton.simulation.physics.math3d import Vec3
from skeleton.simulation.physics.errors import PhysicsValidationError
from skeleton.simulation.physics.world import PhysicsWorld
from .test_simulation_physics_vehicle import _scene


def test_invalid_vehicle_snapshot_does_not_mutate_existing_state():
    world, vehicle, _ = _scene()
    before = vehicle.capture_state()
    for bad in (
        replace(before, steer_angle=float("nan")),
        replace(before, spin_speeds=(float("inf"),) + before.spin_speeds[1:]),
        replace(before, last_grounded=999),
        replace(before, state_digest="0"*64),
    ):
        with pytest.raises(PhysicsValidationError):
            vehicle.restore_state(bad)
        assert vehicle.capture_state() == before


def test_massive_integral_vehicle_inputs_fail_with_domain_error():
    # int -> float overflows for 10**1000; do not leak OverflowError
    # outside the validated physics admission contract.
    for constructor in (
        lambda: VehicleControl(throttle=10**1000),
        lambda: WheelSettings("wheel", Vec3(), radius=10**1000),
        lambda: VehicleSettings((WheelSettings("wheel", Vec3()),),
                                max_drive_force=10**1000),
    ):
        with pytest.raises(PhysicsValidationError, match="finite"):
            constructor()


def test_custom_numeric_protocol_cannot_run_untrusted_float_hook():
    class HostileFloat(float):
        def __float__(self):
            raise AssertionError("untrusted __float__ must not run")
    with pytest.raises(PhysicsValidationError, match="numeric"):
        VehicleControl(steer=HostileFloat(0.5))


def test_large_tick_batch_rejected_before_world_advance():
    world, vehicle, _ = _scene()
    before = world.tick
    with pytest.raises(PhysicsValidationError):
        step_vehicles(world,((vehicle,VehicleControl()),),steps=10001)
    assert world.tick == before


def test_vehicle_identity_and_forged_controls_fail_before_simulation():
    with pytest.raises(PhysicsValidationError):
        RaycastVehicle("../car",VehicleSettings((WheelSettings("wheel",Vec3()),)))
    world, vehicle, _ = _scene()
    with pytest.raises(PhysicsValidationError):
        step_vehicles(world,tuple())
    assert world.tick==0
