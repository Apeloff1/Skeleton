"""Moving finite-convex conservative advancement and rollback regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CapsuleShape,
    ContinuousCollisionDetector,
    ConvexHullShape,
    CylinderShape,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    RigidBody,
    SphereShape,
    Vec3,
)


def _cube_hull(half: float = 0.5) -> ConvexHullShape:
    h = half
    vertices = (
        Vec3(-h, -h, -h),
        Vec3(h, -h, -h),
        Vec3(h, h, -h),
        Vec3(-h, h, -h),
        Vec3(-h, -h, h),
        Vec3(h, -h, h),
        Vec3(h, h, h),
        Vec3(-h, h, h),
    )
    faces = (
        (0, 2, 1), (0, 3, 2),
        (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4),
        (3, 7, 6), (3, 6, 2),
        (0, 4, 7), (0, 7, 3),
        (1, 2, 6), (1, 6, 5),
    )
    return ConvexHullShape(vertices, faces)


def _dynamic(
    body_id: str,
    shape,
    *,
    position: Vec3,
    velocity: Vec3 = Vec3(),
    continuous: bool = False,
) -> RigidBody:
    body = RigidBody.dynamic(
        body_id,
        shape,
        position=position,
        continuous=continuous,
        linear_damping=0.0,
        angular_damping=0.0,
    )
    body.linear_velocity = velocity
    return body


def _static(body_id: str, shape, *, position: Vec3 = Vec3()) -> RigidBody:
    return RigidBody.static(body_id, shape, position=position)


def test_fast_continuous_box_hits_static_box_without_tunneling() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(20.0, 0.0, 0.0),
        continuous=True,
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
    )
    detector = ContinuousCollisionDetector(
        motion_threshold=0.1,
        distance_tolerance=1.0e-7,
    )

    hit = detector.sweep(moving, (moving, target), 0.25)

    assert hit is not None
    assert hit.target_body == "target"
    assert hit.distance == pytest.approx(2.0, abs=2.0e-5)
    assert hit.fraction == pytest.approx(0.4, abs=1.0e-5)
    assert hit.normal.x < -0.999


def test_fast_continuous_capsule_hits_static_box() -> None:
    moving = _dynamic(
        "moving",
        CapsuleShape(0.3, 0.7),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(18.0, 0.0, 0.0),
        continuous=True,
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 1.0, 1.0)),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    hit = detector.sweep(moving, (moving, target), 0.3)

    assert hit is not None
    assert 0.0 < hit.fraction < 1.0
    assert hit.normal.x < -0.99


def test_fast_continuous_hull_hits_static_cylinder() -> None:
    moving = _dynamic(
        "moving",
        _cube_hull(0.4),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(16.0, 0.0, 0.0),
        continuous=True,
    )
    target = _static(
        "target",
        CylinderShape(0.5, 0.8),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    hit = detector.sweep(moving, (moving, target), 0.35)

    assert hit is not None
    assert hit.fraction < 1.0
    assert hit.normal.x < -0.98


def test_conservative_advancement_accounts_for_target_velocity() -> None:
    moving = _dynamic(
        "a",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(10.0, 0.0, 0.0),
        continuous=True,
    )
    target = _dynamic(
        "b",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        position=Vec3(3.0, 0.0, 0.0),
        velocity=Vec3(-10.0, 0.0, 0.0),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    hit = detector.sweep(moving, (moving, target), 0.5)

    assert hit is not None
    assert hit.fraction == pytest.approx(0.5, abs=2.0e-5)
    assert hit.distance == pytest.approx(2.5, abs=2.0e-4)


def test_separating_continuous_convex_pair_has_no_toi() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        position=Vec3(-2.0, 0.0, 0.0),
        velocity=Vec3(-10.0, 0.0, 0.0),
        continuous=True,
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
    )

    assert (
        ContinuousCollisionDetector(motion_threshold=0.1).sweep(
            moving,
            (moving, target),
            0.25,
        )
        is None
    )


def test_motion_threshold_filters_slow_convex_body() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3.one()),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(0.1, 0.0, 0.0),
        continuous=True,
    )
    target = _static("target", BoxShape(Vec3.one()))

    assert (
        ContinuousCollisionDetector(motion_threshold=0.5).sweep(
            moving,
            (moving, target),
            0.1,
        )
        is None
    )


def test_angular_motion_contributes_to_continuous_eligibility() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(2.0, 0.1, 0.1)),
        position=Vec3.zero(),
        continuous=True,
    )
    moving.angular_velocity = Vec3(0.0, 0.0, 4.0)
    target = _static(
        "target",
        SphereShape(0.25),
        position=Vec3(0.9, 1.6, 0.0),
    )
    detector = ContinuousCollisionDetector(
        motion_threshold=0.1,
        convex_iterations=64,
    )

    hit = detector.sweep(moving, (moving, target), 0.5)

    assert hit is not None
    assert 0.0 <= hit.fraction <= 1.0


def test_earliest_event_is_input_order_deterministic_for_convex_pairs() -> None:
    moving = _dynamic(
        "moving",
        CapsuleShape(0.3, 0.6),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(14.0, 0.0, 0.0),
        continuous=True,
    )
    near = _static(
        "near",
        BoxShape(Vec3(0.4, 0.8, 0.8)),
        position=Vec3(0.0, 0.0, 0.0),
    )
    far = _static(
        "far",
        CylinderShape(0.4, 0.8),
        position=Vec3(2.0, 0.0, 0.0),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    forward = detector.earliest_event((moving, near, far), 0.5)
    reverse = detector.earliest_event((far, near, moving), 0.5)

    assert forward is not None
    assert forward == reverse
    assert {forward.body_a, forward.body_b} == {"moving", "near"}


def test_world_step_prevents_fast_box_from_crossing_static_box() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.25,
            ccd_motion_threshold=0.1,
            ccd_convex_iterations=64,
            sleep_after_seconds=10.0,
        )
    )
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(20.0, 0.0, 0.0),
        continuous=True,
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
    )
    world.add_body(moving)
    world.add_body(target)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert moving.position.x < 1.0
    assert moving.linear_velocity.x < 20.0


def test_convex_ccd_policy_is_bound_into_settings_identity() -> None:
    left = PhysicsSettings(ccd_convex_iterations=16)
    right = PhysicsSettings(ccd_convex_iterations=32)
    tolerance = PhysicsSettings(ccd_distance_tolerance=2.0e-6)

    assert left.fingerprint != right.fingerprint
    assert right.fingerprint != tolerance.fingerprint


def test_convex_ccd_rejects_invalid_policy() -> None:
    with pytest.raises(PhysicsValidationError, match="ccd_convex_iterations"):
        PhysicsSettings(ccd_convex_iterations=0)
    with pytest.raises(PhysicsValidationError, match="ccd_distance_tolerance"):
        PhysicsSettings(ccd_distance_tolerance=0.0)
    with pytest.raises(PhysicsValidationError, match="convex_iterations"):
        ContinuousCollisionDetector(convex_iterations=0)
    with pytest.raises(PhysicsValidationError, match="distance_tolerance"):
        ContinuousCollisionDetector(distance_tolerance=0.0)


def test_convex_ccd_iteration_exhaustion_rolls_world_back_exactly() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.25,
            ccd_motion_threshold=0.1,
            ccd_convex_iterations=1,
            ccd_distance_tolerance=1.0e-9,
            sleep_after_seconds=10.0,
        )
    )
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        position=Vec3(-3.0, 0.0, 0.0),
        velocity=Vec3(20.0, 0.0, 0.0),
        continuous=True,
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
    )
    world.add_body(moving)
    world.add_body(target)
    before = world.capture_snapshot()
    digest = world.state_digest

    with pytest.raises(PhysicsValidationError, match="iteration bound"):
        world.step()

    assert world.state_digest == digest
    assert world.capture_snapshot() == before
    assert world.tick == 0
