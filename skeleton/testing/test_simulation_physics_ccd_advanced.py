"""Advanced continuous collision detection and TOI substep regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    ContinuousCollisionDetector,
    PhysicsMaterial,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    RigidBody,
    SphereShape,
    Vec3,
)


def _sphere(
    body_id: str,
    *,
    position: Vec3,
    velocity: Vec3,
    continuous: bool,
    restitution: float = 1.0,
) -> RigidBody:
    body = RigidBody.dynamic(
        body_id,
        SphereShape(0.1),
        position=position,
        material=PhysicsMaterial(friction=0.0, restitution=restitution),
        linear_damping=0.0,
        angular_damping=0.0,
        continuous=continuous,
    )
    body.linear_velocity = velocity
    return body


def test_relative_motion_sphere_toi_matches_analytic_head_on_time() -> None:
    left = _sphere(
        "a",
        position=Vec3(-1.0, 0.0, 0.0),
        velocity=Vec3(200.0, 0.0, 0.0),
        continuous=True,
    )
    right = _sphere(
        "b",
        position=Vec3(1.0, 0.0, 0.0),
        velocity=Vec3(-200.0, 0.0, 0.0),
        continuous=True,
    )
    detector = ContinuousCollisionDetector()
    event = detector.earliest_event((left, right), 0.01)
    assert event is not None
    assert event.body_a == "a"
    assert event.body_b == "b"
    assert event.time == pytest.approx(0.0045, abs=1.0e-12)
    assert event.fraction == pytest.approx(0.45, abs=1.0e-12)
    assert event.normal.x > 0.999999


def test_dynamic_spheres_do_not_tunnel_when_both_are_continuous() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.01,
            sleep_after_seconds=10.0,
            ccd_max_substeps=8,
        )
    )
    left = _sphere(
        "a",
        position=Vec3(-1.0, 0.0, 0.0),
        velocity=Vec3(200.0, 0.0, 0.0),
        continuous=True,
    )
    right = _sphere(
        "b",
        position=Vec3(1.0, 0.0, 0.0),
        velocity=Vec3(-200.0, 0.0, 0.0),
        continuous=True,
    )
    world.add_body(left)
    world.add_body(right)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert left.linear_velocity.x < -199.0
    assert right.linear_velocity.x > 199.0
    assert left.position.x < right.position.x
    assert left.position.x == pytest.approx(-1.2, abs=5.0e-4)
    assert right.position.x == pytest.approx(1.2, abs=5.0e-4)


def test_one_continuous_sphere_catches_noncontinuous_dynamic_target() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.01,
            sleep_after_seconds=10.0,
        )
    )
    left = _sphere(
        "a",
        position=Vec3(-1.0, 0.0, 0.0),
        velocity=Vec3(200.0, 0.0, 0.0),
        continuous=True,
    )
    right = _sphere(
        "b",
        position=Vec3(1.0, 0.0, 0.0),
        velocity=Vec3(-200.0, 0.0, 0.0),
        continuous=False,
    )
    world.add_body(left)
    world.add_body(right)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert left.linear_velocity.x < 0.0
    assert right.linear_velocity.x > 0.0


def test_without_continuous_mode_same_fast_dynamic_spheres_cross() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.01,
            sleep_after_seconds=10.0,
        )
    )
    left = _sphere(
        "a",
        position=Vec3(-1.0, 0.0, 0.0),
        velocity=Vec3(200.0, 0.0, 0.0),
        continuous=False,
    )
    right = _sphere(
        "b",
        position=Vec3(1.0, 0.0, 0.0),
        velocity=Vec3(-200.0, 0.0, 0.0),
        continuous=False,
    )
    world.add_body(left)
    world.add_body(right)

    receipt = world.step()[0]

    assert receipt.ccd_clamps == 0
    assert left.position.x == pytest.approx(1.0)
    assert right.position.x == pytest.approx(-1.0)
    assert left.linear_velocity.x == pytest.approx(200.0)
    assert right.linear_velocity.x == pytest.approx(-200.0)


def test_touching_dynamic_spheres_moving_apart_do_not_emit_zero_time_toi() -> None:
    left = _sphere(
        "a",
        position=Vec3(-0.1, 0.0, 0.0),
        velocity=Vec3(-20.0, 0.0, 0.0),
        continuous=True,
    )
    right = _sphere(
        "b",
        position=Vec3(0.1, 0.0, 0.0),
        velocity=Vec3(20.0, 0.0, 0.0),
        continuous=True,
    )
    detector = ContinuousCollisionDetector()
    assert detector.earliest_event((left, right), 0.1) is None


def test_parallel_fast_spheres_with_equal_velocity_have_no_relative_toi() -> None:
    left = _sphere(
        "a",
        position=Vec3(-1.0, 0.0, 0.0),
        velocity=Vec3(500.0, 0.0, 0.0),
        continuous=True,
    )
    right = _sphere(
        "b",
        position=Vec3(1.0, 0.0, 0.0),
        velocity=Vec3(500.0, 0.0, 0.0),
        continuous=True,
    )
    detector = ContinuousCollisionDetector()
    assert detector.earliest_event((left, right), 0.1) is None


def test_simultaneous_toi_tie_breaks_by_canonical_pair_identity() -> None:
    moving = _sphere(
        "m",
        position=Vec3.zero(),
        velocity=Vec3(100.0, 0.0, 0.0),
        continuous=True,
    )
    target_a = RigidBody.static(
        "a",
        SphereShape(0.1),
        position=Vec3(1.0, 0.0, 0.0),
    )
    target_b = RigidBody.static(
        "b",
        SphereShape(0.1),
        position=Vec3(1.0, 0.0, 0.0),
    )
    detector = ContinuousCollisionDetector()
    event = detector.earliest_event((moving, target_b, target_a), 0.02)
    assert event is not None
    assert (event.body_a, event.body_b) == ("a", "m")


def test_ccd_substep_budget_exhaustion_rolls_back_entire_tick() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.1,
            sleep_after_seconds=10.0,
            ccd_max_substeps=1,
            ccd_min_advance_fraction=1.0e-6,
        )
    )
    world.add_body(
        RigidBody.static(
            "left-wall",
            BoxShape(Vec3(0.02, 1.0, 1.0)),
            position=Vec3(-0.5, 0.0, 0.0),
            material=PhysicsMaterial(friction=0.0, restitution=1.0),
        )
    )
    world.add_body(
        RigidBody.static(
            "right-wall",
            BoxShape(Vec3(0.02, 1.0, 1.0)),
            position=Vec3(0.5, 0.0, 0.0),
            material=PhysicsMaterial(friction=0.0, restitution=1.0),
        )
    )
    ball = _sphere(
        "ball",
        position=Vec3.zero(),
        velocity=Vec3(100.0, 0.0, 0.0),
        continuous=True,
        restitution=1.0,
    )
    world.add_body(ball)

    before_digest = world.state_digest
    before_position = ball.position
    before_velocity = ball.linear_velocity

    with pytest.raises(PhysicsValidationError, match="substep bound"):
        world.step()

    assert world.tick == 0
    assert world.state_digest == before_digest
    assert ball.position == before_position
    assert ball.linear_velocity == before_velocity


def test_ccd_settings_are_bound_into_world_identity() -> None:
    left = PhysicsWorld(PhysicsSettings(ccd_max_substeps=4))
    right = PhysicsWorld(PhysicsSettings(ccd_max_substeps=8))
    assert left.settings.fingerprint != right.settings.fingerprint
    assert left.state_digest != right.state_digest
