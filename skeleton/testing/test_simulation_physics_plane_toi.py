"""Finite-convex versus infinite-plane TOI and CCD regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CapsuleShape,
    ContinuousCollisionDetector,
    ConvexTOIResult,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    RigidBody,
    Vec3,
    convex_plane_time_of_impact,
)


def _dynamic(
    body_id: str,
    shape,
    position: Vec3 = Vec3(),
    orientation: Quat = Quat.identity(),
    *,
    continuous: bool = True,
) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        shape,
        position=position,
        orientation=orientation,
        linear_damping=0.0,
        angular_damping=0.0,
        continuous=continuous,
    )


def test_box_plane_toi_matches_exact_linear_support_time() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    plane = RigidBody.static("plane", PlaneShape())
    box.linear_velocity = Vec3(0.0, -10.0, 0.0)

    hit = convex_plane_time_of_impact(
        box,
        plane,
        0.5,
        distance_tolerance=1.0e-8,
    )

    assert isinstance(hit, ConvexTOIResult)
    assert hit.time == pytest.approx(0.25, abs=2.0e-7)
    assert hit.fraction == pytest.approx(0.5, abs=5.0e-7)
    assert hit.normal == Vec3(0.0, -1.0, 0.0)
    assert hit.point_a.y == pytest.approx(0.0, abs=2.0e-6)
    assert hit.point_b.y == pytest.approx(0.0, abs=2.0e-6)
    assert not hit.initial_overlap


def test_rotation_only_long_box_can_reach_plane() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(2.0, 0.1, 0.1)),
        Vec3(0.0, 1.8, 0.0),
    )
    plane = RigidBody.static("plane", PlaneShape())
    box.angular_velocity = Vec3(0.0, 0.0, math.pi * 0.5)

    hit = convex_plane_time_of_impact(
        box,
        plane,
        1.0,
        max_iterations=64,
        distance_tolerance=1.0e-6,
    )

    assert hit is not None
    assert 0.0 < hit.time < 1.0
    assert hit.normal.y < -0.999999
    assert hit.iterations <= 64


def test_translating_kinematic_plane_can_hit_stationary_convex_body() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    plane = RigidBody.kinematic(
        "plane",
        PlaneShape(),
        linear_velocity=Vec3(0.0, 4.0, 0.0),
    )

    hit = convex_plane_time_of_impact(
        box,
        plane,
        1.0,
        distance_tolerance=1.0e-8,
    )

    assert hit is not None
    assert hit.time == pytest.approx(0.625, abs=2.0e-7)
    assert hit.point_a.y == pytest.approx(2.5, abs=2.0e-6)
    assert hit.point_b.y == pytest.approx(2.5, abs=2.0e-6)


def test_convex_moving_away_from_plane_has_no_toi() -> None:
    capsule = _dynamic(
        "capsule",
        CapsuleShape(0.4, 0.7),
        Vec3(0.0, 1.5, 0.0),
    )
    capsule.linear_velocity = Vec3(0.0, 5.0, 0.0)
    plane = RigidBody.static("plane", PlaneShape())

    assert convex_plane_time_of_impact(capsule, plane, 1.0) is None


def test_rotating_infinite_plane_fails_closed() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3.one()),
        Vec3(0.0, 2.0, 0.0),
    )
    plane = RigidBody.kinematic(
        "plane",
        PlaneShape(),
        angular_velocity=Vec3(0.0, 0.0, 0.1),
    )

    with pytest.raises(PhysicsValidationError, match="rotating infinite plane"):
        convex_plane_time_of_impact(box, plane, 1.0)


def test_initial_plane_overlap_returns_zero_time() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 0.25, 0.0),
    )
    plane = RigidBody.static("plane", PlaneShape())

    hit = convex_plane_time_of_impact(box, plane, 0.25)

    assert hit is not None
    assert hit.time == 0.0
    assert hit.fraction == 0.0
    assert hit.initial_overlap


def test_global_ccd_detects_fast_box_against_plane() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    plane = RigidBody.static("plane", PlaneShape())
    box.linear_velocity = Vec3(0.0, -10.0, 0.0)
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((plane, box), 0.5)

    assert event is not None
    assert (event.body_a, event.body_b) == ("box", "plane")
    assert event.time == pytest.approx(0.25, abs=2.0e-6)
    assert event.normal.y < -0.999999


def test_relative_pair_admission_catches_moving_plane_against_stationary_box() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    plane = RigidBody.kinematic(
        "plane",
        PlaneShape(),
        linear_velocity=Vec3(0.0, 4.0, 0.0),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((box, plane), 1.0)

    assert event is not None
    assert event.time == pytest.approx(0.625, abs=3.0e-6)


def test_noncontinuous_stationary_box_is_not_promoted_by_moving_plane() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
        continuous=False,
    )
    plane = RigidBody.kinematic(
        "plane",
        PlaneShape(),
        linear_velocity=Vec3(0.0, 4.0, 0.0),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    assert detector.earliest_event((box, plane), 1.0) is None


def test_zero_time_plane_overlap_moving_out_is_left_to_discrete_solver() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 0.25, 0.0),
    )
    box.linear_velocity = Vec3(0.0, 5.0, 0.0)
    plane = RigidBody.static("plane", PlaneShape())
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    assert detector.earliest_event((box, plane), 0.5) is None


def test_plane_event_normal_flips_with_lexical_body_order() -> None:
    box = _dynamic(
        "z-box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    box.linear_velocity = Vec3(0.0, -10.0, 0.0)
    plane = RigidBody.static("a-plane", PlaneShape())
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((box, plane), 0.5)

    assert event is not None
    assert (event.body_a, event.body_b) == ("a-plane", "z-box")
    assert event.normal.y > 0.999999


def test_world_ccd_prevents_fast_box_tunneling_through_plane() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.5,
            ccd_motion_threshold=0.1,
            ccd_contact_slop=1.0e-6,
            ccd_max_substeps=8,
            sleep_after_seconds=10.0,
        )
    )
    plane = RigidBody.static("plane", PlaneShape())
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    box.linear_velocity = Vec3(0.0, -10.0, 0.0)
    world.add_body(plane)
    world.add_body(box)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert box.position.y > 0.35
    assert box.linear_velocity.y > -10.0


def test_world_ccd_handles_stationary_box_hit_by_kinematic_plane() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0,
            ccd_motion_threshold=0.1,
            ccd_contact_slop=1.0e-6,
            ccd_max_substeps=8,
            sleep_after_seconds=10.0,
        )
    )
    plane = RigidBody.kinematic(
        "plane",
        PlaneShape(),
        linear_velocity=Vec3(0.0, 4.0, 0.0),
    )
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    world.add_body(plane)
    world.add_body(box)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert box.linear_velocity.y > 0.0
