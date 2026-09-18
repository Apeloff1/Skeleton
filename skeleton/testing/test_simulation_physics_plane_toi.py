"""Finite-convex versus static-plane continuous-collision regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CapsuleShape,
    ContinuousCollisionDetector,
    PhysicsSettings,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    Vec3,
)


def _dynamic(
    body_id: str,
    shape,
    position: Vec3,
    *,
    continuous: bool = True,
) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        shape,
        position=position,
        continuous=continuous,
        linear_damping=0.0,
        angular_damping=0.0,
    )


def _plane(body_id: str, height: float = 0.0) -> RigidBody:
    return RigidBody.static(
        body_id,
        PlaneShape(),
        position=Vec3(0.0, height, 0.0),
    )


def test_downward_box_plane_toi_matches_exact_support_time() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 2.0, 0.0),
    )
    box.linear_velocity = Vec3(0.0, -4.0, 0.0)
    floor = _plane("floor")
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((box, floor), 0.5)

    assert event is not None
    assert event.time == pytest.approx(0.375, abs=2.0e-6)
    assert {event.body_a, event.body_b} == {"box", "floor"}


def test_downward_capsule_plane_toi_uses_deepest_support() -> None:
    capsule = _dynamic(
        "capsule",
        CapsuleShape(0.5, 0.8),
        Vec3(0.0, 3.0, 0.0),
    )
    capsule.linear_velocity = Vec3(0.0, -4.0, 0.0)
    floor = _plane("floor")
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((floor, capsule), 0.75)

    assert event is not None
    assert event.time == pytest.approx(0.425, abs=3.0e-6)


def test_rotation_only_long_box_can_strike_plane() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(2.0, 0.1, 0.1)),
        Vec3(0.0, 1.5, 0.0),
    )
    box.angular_velocity = Vec3(0.0, 0.0, math.pi * 0.5)
    floor = _plane("floor")
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((floor, box), 1.0)

    assert event is not None
    assert 0.0 < event.time < 1.0


def test_plane_event_normal_follows_canonical_a_to_b_order() -> None:
    box = _dynamic(
        "z-box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 2.0, 0.0),
    )
    box.linear_velocity = Vec3(0.0, -5.0, 0.0)
    floor = _plane("a-floor")
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((box, floor), 0.5)

    assert event is not None
    assert (event.body_a, event.body_b) == ("a-floor", "z-box")
    assert event.normal == Vec3.axis(1)


def test_plane_event_normal_flips_when_convex_id_is_first() -> None:
    box = _dynamic(
        "a-box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 2.0, 0.0),
    )
    box.linear_velocity = Vec3(0.0, -5.0, 0.0)
    floor = _plane("z-floor")
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((floor, box), 0.5)

    assert event is not None
    assert (event.body_a, event.body_b) == ("a-box", "z-floor")
    assert event.normal == -Vec3.axis(1)


def test_convex_plane_zero_time_separating_contact_is_suppressed() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 0.5, 0.0),
    )
    box.linear_velocity = Vec3(0.0, 4.0, 0.0)
    floor = _plane("floor")
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    assert detector.earliest_event((box, floor), 0.5) is None


def test_noncontinuous_box_does_not_use_convex_plane_ccd() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 2.0, 0.0),
        continuous=False,
    )
    box.linear_velocity = Vec3(0.0, -20.0, 0.0)
    floor = _plane("floor")
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    assert detector.earliest_event((box, floor), 0.25) is None


def test_global_ccd_selects_higher_plane_first() -> None:
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    box.linear_velocity = Vec3(0.0, -10.0, 0.0)
    low = _plane("low", 0.0)
    high = _plane("high", 1.0)
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((low, box, high), 0.5)

    assert event is not None
    assert {event.body_a, event.body_b} == {"box", "high"}
    assert event.time == pytest.approx(0.15, abs=2.0e-6)


def test_world_ccd_prevents_fast_box_from_crossing_floor() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.25,
            ccd_motion_threshold=0.1,
            ccd_contact_slop=1.0e-6,
            ccd_max_substeps=8,
            sleep_after_seconds=10.0,
        )
    )
    floor = _plane("floor")
    box = _dynamic(
        "box",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
        Vec3(0.0, 3.0, 0.0),
    )
    box.linear_velocity = Vec3(0.0, -20.0, 0.0)
    world.add_body(floor)
    world.add_body(box)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert box.position.y > 0.45
    assert box.linear_velocity.y > -20.0


def test_world_rotation_only_plane_toi_is_resolved() -> None:
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
    floor = _plane("floor")
    box = _dynamic(
        "box",
        BoxShape(Vec3(2.0, 0.1, 0.1)),
        Vec3(0.0, 1.5, 0.0),
    )
    box.angular_velocity = Vec3(0.0, 0.0, math.pi * 0.5)
    world.add_body(floor)
    world.add_body(box)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
