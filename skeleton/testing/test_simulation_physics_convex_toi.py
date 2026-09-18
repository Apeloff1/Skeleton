"""Convex witness-distance and conservative-advancement TOI regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CapsuleShape,
    ContinuousCollisionDetector,
    ConvexDistanceResult,
    ConvexTOIResult,
    CylinderShape,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    Quat,
    RigidBody,
    SphereShape,
    Vec3,
    convex_distance,
    convex_time_of_impact,
)


def _static(body_id: str, shape, position: Vec3 = Vec3(), orientation: Quat = Quat.identity()):
    return RigidBody.static(
        body_id,
        shape,
        position=position,
        orientation=orientation,
    )


def _dynamic(body_id: str, shape, position: Vec3 = Vec3(), orientation: Quat = Quat.identity()):
    return RigidBody.dynamic(
        body_id,
        shape,
        position=position,
        orientation=orientation,
        linear_damping=0.0,
        angular_damping=0.0,
        continuous=True,
    )


def test_convex_distance_spheres_returns_exact_gap_normal_and_witnesses() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(3.0, 0.0, 0.0))

    result = convex_distance(a, b)

    assert isinstance(result, ConvexDistanceResult)
    assert not result.intersects
    assert result.distance == pytest.approx(1.0, abs=1.0e-10)
    assert result.normal == Vec3.axis(0)
    assert result.point_a == Vec3(1.0, 0.0, 0.0)
    assert result.point_b == Vec3(2.0, 0.0, 0.0)
    assert 1 <= result.simplex_size <= 4


def test_convex_distance_pair_reversal_swaps_witnesses_and_normal() -> None:
    a = _static("a", CapsuleShape(0.4, 0.8), Vec3(-1.5, 0.2, 0.0))
    b = _static(
        "b",
        CylinderShape(0.5, 0.6),
        Vec3(1.2, -0.1, 0.3),
        Quat.from_axis_angle(Vec3.axis(2), 0.2),
    )

    forward = convex_distance(a, b)
    reverse = convex_distance(b, a)

    assert not forward.intersects
    assert not reverse.intersects
    assert reverse.distance == pytest.approx(forward.distance, rel=1.0e-8, abs=1.0e-9)
    assert reverse.normal.dot(forward.normal) < -0.999999
    assert reverse.point_a.almost_equal(forward.point_b, tolerance=1.0e-7)
    assert reverse.point_b.almost_equal(forward.point_a, tolerance=1.0e-7)


def test_convex_distance_axis_aligned_boxes_returns_exact_face_gap() -> None:
    a = _static("a", BoxShape(Vec3(1.0, 0.5, 0.5)))
    b = _static(
        "b",
        BoxShape(Vec3(1.0, 0.5, 0.5)),
        Vec3(4.0, 0.0, 0.0),
    )

    result = convex_distance(a, b)

    assert not result.intersects
    assert result.distance == pytest.approx(2.0, abs=1.0e-9)
    assert result.normal.x > 0.999999
    assert result.point_a.x == pytest.approx(1.0)
    assert result.point_b.x == pytest.approx(3.0)
    assert (result.point_b - result.point_a).length() == pytest.approx(result.distance)


def test_convex_distance_touching_shapes_report_zero_distance() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(2.0, 0.0, 0.0))

    result = convex_distance(a, b)

    assert result.intersects
    assert result.distance == 0.0
    assert result.normal.x > 0.999999


def test_convex_distance_overlap_reports_intersection() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(1.5, 0.0, 0.0))

    result = convex_distance(a, b)

    assert result.intersects
    assert result.distance == 0.0


def test_convex_distance_is_deterministic_for_rotated_round_shapes() -> None:
    a = _static(
        "a",
        CapsuleShape(0.5, 1.0),
        Vec3(-1.3, 0.4, 0.2),
        Quat.from_axis_angle(Vec3.axis(2), 0.31),
    )
    b = _static(
        "b",
        CylinderShape(0.45, 0.9),
        Vec3(1.4, -0.2, -0.1),
        Quat.from_axis_angle(Vec3.axis(0), -0.27),
    )

    first = convex_distance(a, b)
    second = convex_distance(a, b)

    assert first == second


def test_linear_box_toi_matches_exact_face_contact_time() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-3.0, 0.0, 0.0),
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3.zero(),
    )
    moving.linear_velocity = Vec3(10.0, 0.0, 0.0)

    hit = convex_time_of_impact(
        moving,
        target,
        0.5,
        distance_tolerance=1.0e-7,
    )

    assert isinstance(hit, ConvexTOIResult)
    assert hit.time == pytest.approx(0.2, abs=2.0e-6)
    assert hit.fraction == pytest.approx(0.4, abs=5.0e-6)
    assert hit.normal.x > 0.999999
    assert not hit.initial_overlap


def test_two_moving_boxes_use_relative_closing_motion() -> None:
    left = _dynamic(
        "left",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-3.0, 0.0, 0.0),
    )
    right = _dynamic(
        "right",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(3.0, 0.0, 0.0),
    )
    left.linear_velocity = Vec3(10.0, 0.0, 0.0)
    right.linear_velocity = Vec3(-10.0, 0.0, 0.0)

    hit = convex_time_of_impact(
        left,
        right,
        0.5,
        distance_tolerance=1.0e-7,
    )

    assert hit is not None
    assert hit.time == pytest.approx(0.25, abs=2.0e-6)
    assert hit.normal.x > 0.999999


def test_capsule_cylinder_linear_toi_returns_finite_witnesses() -> None:
    capsule = _dynamic(
        "capsule",
        CapsuleShape(0.4, 0.8),
        Vec3(-3.0, 0.1, 0.0),
        Quat.from_axis_angle(Vec3.axis(2), 0.15),
    )
    cylinder = _static(
        "cylinder",
        CylinderShape(0.5, 0.7),
        Vec3.zero(),
        Quat.from_axis_angle(Vec3.axis(0), -0.1),
    )
    capsule.linear_velocity = Vec3(8.0, 0.0, 0.0)

    hit = convex_time_of_impact(capsule, cylinder, 0.5)

    assert hit is not None
    assert 0.0 < hit.time < 0.5
    assert hit.normal.length() == pytest.approx(1.0)
    assert all(math.isfinite(value) for value in hit.point_a.to_tuple())
    assert all(math.isfinite(value) for value in hit.point_b.to_tuple())


def test_rotation_only_box_can_generate_toi_from_angular_sweep_bound() -> None:
    rotating = _dynamic(
        "rotating",
        BoxShape(Vec3(2.0, 0.1, 0.1)),
        Vec3.zero(),
    )
    target = _static(
        "target",
        SphereShape(0.2),
        Vec3(0.0, 1.8, 0.0),
    )
    rotating.angular_velocity = Vec3(0.0, 0.0, math.pi * 0.5)

    initial = convex_distance(rotating, target)
    assert not initial.intersects

    hit = convex_time_of_impact(
        rotating,
        target,
        1.0,
        max_iterations=64,
        distance_tolerance=1.0e-5,
    )

    assert hit is not None
    assert 0.0 < hit.time < 1.0
    assert hit.iterations <= 64


def test_moving_apart_convex_pair_has_no_toi() -> None:
    left = _dynamic(
        "left",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-2.0, 0.0, 0.0),
    )
    right = _static(
        "right",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(2.0, 0.0, 0.0),
    )
    left.linear_velocity = Vec3(-5.0, 0.0, 0.0)

    assert convex_time_of_impact(left, right, 1.0) is None


def test_initial_overlap_convex_toi_is_zero_time() -> None:
    a = _dynamic("a", BoxShape(Vec3.one()), Vec3.zero())
    b = _static("b", BoxShape(Vec3.one()), Vec3(0.5, 0.0, 0.0))

    hit = convex_time_of_impact(a, b, 0.25)

    assert hit is not None
    assert hit.time == 0.0
    assert hit.fraction == 0.0
    assert hit.initial_overlap


def test_convex_toi_is_deterministic_for_same_motion() -> None:
    moving = _dynamic(
        "moving",
        CylinderShape(0.5, 0.8),
        Vec3(-2.5, 0.2, 0.1),
        Quat.from_axis_angle(Vec3.axis(2), 0.2),
    )
    target = _static(
        "target",
        CapsuleShape(0.45, 0.7),
        Vec3(0.5, -0.1, -0.05),
        Quat.from_axis_angle(Vec3.axis(0), -0.15),
    )
    moving.linear_velocity = Vec3(6.0, -0.2, 0.1)
    moving.angular_velocity = Vec3(0.1, 0.3, 0.2)

    first = convex_time_of_impact(moving, target, 0.75, max_iterations=64)
    second = convex_time_of_impact(moving, target, 0.75, max_iterations=64)

    assert first == second


def test_convex_distance_and_toi_validate_bounds() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(3.0, 0.0, 0.0))

    with pytest.raises(PhysicsValidationError, match="max_iterations"):
        convex_distance(a, b, max_iterations=0)
    with pytest.raises(PhysicsValidationError, match="tolerance"):
        convex_distance(a, b, tolerance=0.0)
    with pytest.raises(PhysicsValidationError, match="dt"):
        convex_time_of_impact(a, b, 0.0)
    with pytest.raises(PhysicsValidationError, match="max_iterations"):
        convex_time_of_impact(a, b, 1.0, max_iterations=0)
    with pytest.raises(PhysicsValidationError, match="distance_iterations"):
        convex_time_of_impact(a, b, 1.0, distance_iterations=0)



def test_global_ccd_emits_moving_box_toi() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-3.0, 0.0, 0.0),
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3.zero(),
    )
    moving.linear_velocity = Vec3(10.0, 0.0, 0.0)
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((target, moving), 0.5)

    assert event is not None
    assert (event.body_a, event.body_b) == ("moving", "target")
    assert event.time == pytest.approx(0.2, abs=2.0e-6)
    assert event.normal.x > 0.999999


def test_global_ccd_handles_continuous_box_against_moving_discrete_box() -> None:
    left = _dynamic(
        "a",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-3.0, 0.0, 0.0),
    )
    right = _dynamic(
        "b",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(3.0, 0.0, 0.0),
    )
    right.continuous = False
    left.linear_velocity = Vec3(10.0, 0.0, 0.0)
    right.linear_velocity = Vec3(-5.0, 0.0, 0.0)
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((right, left), 0.5)

    assert event is not None
    assert (event.body_a, event.body_b) == ("a", "b")
    assert event.time == pytest.approx(1.0 / 3.0, abs=3.0e-6)


def test_global_ccd_detects_rotation_only_continuous_box() -> None:
    rotating = _dynamic(
        "a",
        BoxShape(Vec3(2.0, 0.1, 0.1)),
        Vec3.zero(),
    )
    target = _static(
        "b",
        SphereShape(0.2),
        Vec3(0.0, 1.8, 0.0),
    )
    rotating.angular_velocity = Vec3(0.0, 0.0, math.pi * 0.5)
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((target, rotating), 1.0)

    assert event is not None
    assert 0.0 < event.time < 1.0
    assert (event.body_a, event.body_b) == ("a", "b")


def test_noncontinuous_fast_box_does_not_enter_general_ccd() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-3.0, 0.0, 0.0),
    )
    moving.continuous = False
    moving.linear_velocity = Vec3(20.0, 0.0, 0.0)
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3.zero(),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    assert detector.earliest_event((moving, target), 0.5) is None


def test_zero_time_separating_convex_overlap_is_left_to_discrete_solver() -> None:
    moving = _dynamic(
        "a",
        BoxShape(Vec3.one()),
        Vec3.zero(),
    )
    target = _static(
        "b",
        BoxShape(Vec3.one()),
        Vec3(0.5, 0.0, 0.0),
    )
    moving.linear_velocity = Vec3(-5.0, 0.0, 0.0)
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    assert detector.earliest_event((moving, target), 0.25) is None


def test_world_ccd_prevents_fast_box_tunneling_through_static_box() -> None:
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
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-3.0, 0.0, 0.0),
    )
    moving.linear_velocity = Vec3(10.0, 0.0, 0.0)
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3.zero(),
    )
    world.add_body(moving)
    world.add_body(target)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert moving.position.x < target.position.x
    assert moving.position.x < -0.8
    assert moving.linear_velocity.x < 10.0


def test_world_ccd_resolves_fast_capsule_against_static_cylinder() -> None:
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
    moving = _dynamic(
        "capsule",
        CapsuleShape(0.4, 0.7),
        Vec3(-3.0, 0.0, 0.0),
        Quat.from_axis_angle(Vec3.axis(2), 0.1),
    )
    moving.linear_velocity = Vec3(9.0, 0.0, 0.0)
    target = _static(
        "cylinder",
        CylinderShape(0.5, 0.8),
        Vec3.zero(),
        Quat.from_axis_angle(Vec3.axis(0), -0.1),
    )
    world.add_body(moving)
    world.add_body(target)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert moving.position.x < target.position.x
    assert moving.linear_velocity.x < 9.0


def test_general_convex_toi_tie_break_is_canonical() -> None:
    moving = _dynamic(
        "m",
        BoxShape(Vec3(0.25, 0.25, 0.25)),
        Vec3(-2.0, 0.0, 0.0),
    )
    moving.linear_velocity = Vec3(10.0, 0.0, 0.0)
    target_a = _static(
        "a",
        BoxShape(Vec3(0.25, 0.25, 0.25)),
        Vec3.zero(),
    )
    target_b = _static(
        "b",
        BoxShape(Vec3(0.25, 0.25, 0.25)),
        Vec3.zero(),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((target_b, moving, target_a), 0.5)

    assert event is not None
    assert {event.body_a, event.body_b} == {"a", "m"}



def test_separating_translation_can_dominate_angular_sweep_bound() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-2.0, 0.0, 0.0),
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(2.0, 0.0, 0.0),
    )
    moving.linear_velocity = Vec3(-5.0, 0.0, 0.0)
    moving.angular_velocity = Vec3(0.0, 0.0, 1.0)

    hit = convex_time_of_impact(
        moving,
        target,
        0.5,
        max_iterations=8,
    )

    assert hit is None



def test_convex_toi_fallback_scan_recovers_after_advancement_budget() -> None:
    moving = _dynamic(
        "moving",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(-3.0, 0.0, 0.0),
    )
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3.zero(),
    )
    moving.linear_velocity = Vec3(10.0, 0.0, 0.0)

    hit = convex_time_of_impact(
        moving,
        target,
        0.5,
        max_iterations=1,
        distance_tolerance=1.0e-7,
        time_tolerance=1.0e-9,
    )

    assert hit is not None
    assert hit.time == pytest.approx(0.2, abs=2.0e-6)
    assert hit.normal.x > 0.999999
    assert hit.iterations > 1
