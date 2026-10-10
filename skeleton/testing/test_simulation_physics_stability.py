"""Fixed-step stability: deterministic sleep/wake and energy-drift guard."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    DistanceJoint,
    EnergyDriftMonitor,
    EnergyGuardMode,
    PhysicsMaterial,
    PhysicsSettings,
    PhysicsStabilityError,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    SphereShape,
    SpringJoint,
    Vec3,
)

DT = 1.0 / 60.0


def _sphere(
    body_id: str,
    position: Vec3,
    *,
    restitution: float = 0.0,
    radius: float = 0.5,
) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        SphereShape(radius),
        position=position,
        material=PhysicsMaterial(friction=0.5, restitution=restitution),
        linear_damping=0.0,
        angular_damping=0.0,
    )


def _resting_world(**settings: object) -> tuple[PhysicsWorld, RigidBody]:
    world = PhysicsWorld(PhysicsSettings(sleep_after_seconds=0.25, **settings))
    world.add_body(RigidBody.static("ground", PlaneShape()))
    body = world.add_body(_sphere("ball", Vec3(0.0, 0.5, 0.0)))
    return world, body


def _first_sleep_tick(world: PhysicsWorld, body: RigidBody, limit: int) -> int | None:
    for _ in range(limit):
        receipt = world.step()[0]
        if not body.awake:
            return receipt.tick
    return None


# --- settings -------------------------------------------------------------


def test_sleep_after_steps_counts_whole_fixed_steps() -> None:
    assert PhysicsSettings().sleep_after_steps == 45
    assert PhysicsSettings(fixed_dt=0.1, sleep_after_seconds=0.2).sleep_after_steps == 2
    assert PhysicsSettings(fixed_dt=0.1, sleep_after_seconds=0.25).sleep_after_steps == 3
    assert PhysicsSettings(fixed_dt=1.0, sleep_after_seconds=0.01).sleep_after_steps == 1


def test_energy_guard_settings_validate_and_fingerprint() -> None:
    assert PhysicsSettings(energy_guard="clamp").energy_guard is EnergyGuardMode.CLAMP
    with pytest.raises(PhysicsValidationError):
        PhysicsSettings(energy_guard="explode")
    with pytest.raises(PhysicsValidationError):
        PhysicsSettings(energy_growth_tolerance=-0.1)
    with pytest.raises(PhysicsValidationError):
        PhysicsSettings(sleep_velocity_change=float("nan"))
    assert (
        PhysicsSettings(energy_guard=EnergyGuardMode.REPORT).fingerprint
        != PhysicsSettings().fingerprint
    )


def test_total_solver_iteration_budget_is_bounded() -> None:
    PhysicsSettings(velocity_iterations=64, position_iterations=64,
                    constraint_velocity_iterations=64, constraint_position_iterations=64)
    with pytest.raises(PhysicsValidationError, match="iterations"):
        PhysicsSettings(
            velocity_iterations=128,
            position_iterations=128,
            constraint_velocity_iterations=1,
            constraint_position_iterations=1,
        )


# --- sleeping -------------------------------------------------------------


def test_resting_contact_body_sleeps_on_exact_quiet_step_count() -> None:
    # Regression: contact impulses called RigidBody.wake(), which zeroed the
    # quiet timer every step, so bodies resting on the ground never slept.
    world, ball = _resting_world()
    tick = _first_sleep_tick(world, ball, 120)
    assert tick is not None
    assert tick >= world.settings.sleep_after_steps
    assert ball.linear_velocity == Vec3.zero()
    receipt = world.step()[0]
    assert receipt.sleeping_bodies == 1
    assert receipt.stability.bodies_put_to_sleep == 0


def test_sleep_tick_is_deterministic_across_worlds() -> None:
    left, left_ball = _resting_world()
    right, right_ball = _resting_world()
    assert _first_sleep_tick(left, left_ball, 120) == _first_sleep_tick(
        right, right_ball, 120
    )
    assert left.state_digest == right.state_digest


def test_sleeping_island_is_frozen_and_not_solved() -> None:
    world, ball = _resting_world()
    assert _first_sleep_tick(world, ball, 120) is not None
    position = ball.position
    receipts = world.step(20)
    assert not ball.awake
    assert ball.position == position
    assert all(row.solver.normal_impulses == 0 for row in receipts)


def test_sustained_force_into_ground_prevents_false_sleep() -> None:
    world, ball = _resting_world()
    for _ in range(60):
        ball.apply_force(Vec3(0.0, -5.0, 0.0))
        world.step()
        assert ball.awake
        assert ball.sleep_time == 0.0
    # Once the push stops the body is free to sleep again.
    assert _first_sleep_tick(world, ball, 120) is not None


def test_velocity_change_gate_measures_in_step_solver_disturbance() -> None:
    # The per-step velocity change compares start-of-step velocity with the
    # post-solve velocity, so it sees what the contact solver did inside the
    # step even when both speeds are under the sleep speed limit. Nudging the
    # resting ball into the ground at 0.02 m/s every step is a 0.02 m/s
    # in-step disturbance: quiet under the default gate, disturbed under a
    # 0.01 m/s gate. An undisturbed resting body has exactly zero change.
    def first_sleep_tick_with_nudge(change: float) -> int | None:
        world, ball = _resting_world(sleep_velocity_change=change)
        for _ in range(120):
            ball.linear_velocity = Vec3(0.0, -0.02, 0.0)
            receipt = world.step()[0]
            if not ball.awake:
                return receipt.tick
        return None

    assert first_sleep_tick_with_nudge(0.05) is not None
    assert first_sleep_tick_with_nudge(0.01) is None
    strict_world, strict_ball = _resting_world(sleep_velocity_change=0.0)
    assert _first_sleep_tick(strict_world, strict_ball, 120) is not None


def test_impulse_wakes_whole_sleeping_island_deterministically() -> None:
    def run() -> tuple[str, tuple[bool, bool]]:
        world = PhysicsWorld(
            PhysicsSettings(gravity=Vec3.zero(), fixed_dt=0.1, sleep_after_seconds=0.2)
        )
        a = world.add_body(_sphere("a", Vec3(-1.0, 0.0, 0.0)))
        b = world.add_body(_sphere("b", Vec3(1.0, 0.0, 0.0)))
        world.add_joint(DistanceJoint("link", "a", "b", rest_length=2.0))
        world.step(3)
        assert not a.awake and not b.awake
        a.apply_impulse(Vec3(0.0, 2.0, 0.0))
        world.step()
        return world.state_digest, (a.awake, b.awake)

    first = run()
    assert first == run()
    assert first[1] == (True, True)


def test_moving_kinematic_body_wakes_sleeping_body_on_contact() -> None:
    world = PhysicsWorld(
        PhysicsSettings(gravity=Vec3.zero(), sleep_after_seconds=0.1)
    )
    crate = world.add_body(_sphere("crate", Vec3(0.0, 0.0, 0.0)))
    world.step(10)
    assert not crate.awake
    world.add_body(
        RigidBody.kinematic(
            "pusher",
            SphereShape(0.5),
            position=Vec3(-1.2, 0.0, 0.0),
            linear_velocity=Vec3(3.0, 0.0, 0.0),
        )
    )
    woken = 0
    for _ in range(30):
        woken += world.step()[0].stability.bodies_woken_by_kinematic
    assert woken >= 1
    assert crate.position.x > 0.2
    pusher = world.get_body("pusher")
    # The crate was pushed ahead of the platform instead of being tunnelled.
    assert crate.position.x - pusher.position.x > 0.9


# --- energy guard ----------------------------------------------------------


def test_free_fall_energy_never_grows_over_many_steps() -> None:
    world = PhysicsWorld(PhysicsSettings(energy_guard=EnergyGuardMode.RAISE))
    world.add_body(_sphere("fall", Vec3(0.0, 100.0, 0.0)))
    monitor = EnergyDriftMonitor(world)
    for _ in range(120):
        receipt = world.step()[0]
        monitor.observe()
        assert not receipt.stability.runaway
        assert receipt.stability.monitored_bodies == 1
    assert monitor.bounded(gain_tolerance=1.0e-9)
    # Semi-implicit Euler under uniform gravity is slightly dissipative.
    assert monitor.final_drift <= 0.0


def test_drop_and_settle_energy_drift_is_bounded() -> None:
    world = PhysicsWorld(PhysicsSettings(energy_guard=EnergyGuardMode.REPORT))
    world.add_body(RigidBody.static("ground", PlaneShape()))
    ball = world.add_body(_sphere("drop", Vec3(0.0, 2.0, 0.0), restitution=0.5))
    monitor = EnergyDriftMonitor(world)
    runaways = 0
    for _ in range(240):
        runaways += world.step()[0].stability.runaway
        monitor.observe()
    slop = ball.mass * 9.81 * world.settings.energy_position_slop
    assert runaways == 0
    assert monitor.max_gain <= slop
    assert monitor.final_drift < 0.0
    assert not ball.awake


def test_external_force_work_is_within_allowance() -> None:
    world = PhysicsWorld(
        PhysicsSettings(gravity=Vec3.zero(), energy_guard=EnergyGuardMode.RAISE)
    )
    rocket = world.add_body(_sphere("rocket", Vec3()))
    for _ in range(60):
        rocket.apply_force(Vec3(50.0, 0.0, 10.0), point=Vec3(0.0, 0.5, 0.0))
        receipt = world.step()[0]
        assert receipt.stability.energy_delta > 0.0
        assert not receipt.stability.runaway


def _deep_penetration_world(mode: EnergyGuardMode) -> tuple[PhysicsWorld, RigidBody]:
    world = PhysicsWorld(PhysicsSettings(energy_guard=mode, sleep_after_seconds=10.0))
    world.add_body(RigidBody.static("ground", PlaneShape()))
    # Spawned half-buried: position correction lifts it far faster than any
    # legitimate source could, i.e. a solver energy injection.
    body = world.add_body(_sphere("buried", Vec3(0.0, 0.05, 0.0)))
    return world, body


def test_report_mode_flags_position_correction_pop() -> None:
    world, _ = _deep_penetration_world(EnergyGuardMode.REPORT)
    receipt = world.step()[0]
    assert receipt.stability.runaway
    assert receipt.stability.energy_excess > 0.0
    assert not receipt.stability.clamped


def test_clamp_mode_removes_excess_kinetic_energy() -> None:
    world, body = _deep_penetration_world(EnergyGuardMode.CLAMP)
    body.linear_velocity = Vec3(0.0, 3.0, 0.0)
    reported, _ = _deep_penetration_world(EnergyGuardMode.REPORT)
    reported.get_body("buried").linear_velocity = Vec3(0.0, 3.0, 0.0)

    clamped_receipt = world.step()[0]
    reported_receipt = reported.step()[0]
    assert clamped_receipt.stability.clamped
    assert 0.0 <= clamped_receipt.stability.velocity_scale < 1.0
    assert body.linear_velocity.length() < reported.get_body("buried").linear_velocity.length()
    assert clamped_receipt.stability.energy_after < reported_receipt.stability.energy_after


def test_raise_mode_rolls_back_the_step_exactly() -> None:
    world, _ = _deep_penetration_world(EnergyGuardMode.RAISE)
    before = world.state_digest
    with pytest.raises(PhysicsStabilityError, match="energy runaway"):
        world.step()
    assert world.state_digest == before
    assert world.tick == 0


def test_spring_islands_are_excluded_from_runaway_checks() -> None:
    world = PhysicsWorld(
        PhysicsSettings(gravity=Vec3.zero(), energy_guard=EnergyGuardMode.RAISE)
    )
    world.add_body(_sphere("a", Vec3(-0.5, 0.0, 0.0), radius=0.1))
    world.add_body(_sphere("b", Vec3(0.5, 0.0, 0.0), radius=0.1))
    world.add_joint(SpringJoint("spring", "a", "b", rest_length=3.0, stiffness=200.0))
    receipts = world.step(30)
    assert all(row.stability.unmonitored_bodies == 2 for row in receipts)
    assert all(row.stability.monitored_bodies == 0 for row in receipts)


# --- replay determinism ---------------------------------------------------


def _scenario() -> PhysicsWorld:
    world = PhysicsWorld(
        PhysicsSettings(energy_guard=EnergyGuardMode.CLAMP, sleep_after_seconds=0.2)
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    # a/b bounce and roll well clear of the sweeper's path.
    world.add_body(_sphere("a", Vec3(4.0, 1.5, 0.0), restitution=0.3))
    world.add_body(_sphere("b", Vec3(4.3, 3.0, 0.0), restitution=0.3))
    # c starts slightly sunk (position-correction pop), falls asleep, and is
    # then woken by the kinematic sweeper reaching it around tick 60.
    world.add_body(_sphere("c", Vec3(-1.5, 0.05, 0.0)))
    world.add_body(
        RigidBody.kinematic(
            "sweeper",
            SphereShape(0.5),
            position=Vec3(-4.0, 0.5, 0.0),
            linear_velocity=Vec3(1.5, 0.0, 0.0),
        )
    )
    return world


def _trace(world: PhysicsWorld, steps: int) -> list[tuple[str, dict[str, object]]]:
    return [
        (row.after_digest, row.stability.state_record())
        for row in world.step(steps)
    ]


def test_replay_with_sleep_wake_and_guard_is_bit_identical() -> None:
    left = _trace(_scenario(), 180)
    right = _trace(_scenario(), 180)
    assert left == right
    assert any(record["bodies_put_to_sleep"] for _, record in left)
    assert any(record["bodies_woken_by_kinematic"] for _, record in left)


def test_snapshot_restore_replays_identically_across_sleep_boundary() -> None:
    world = _scenario()
    world.step(60)
    snapshot = world.capture_snapshot()
    expected = _trace(world, 90)
    world.restore_snapshot(snapshot)
    assert _trace(world, 90) == expected
