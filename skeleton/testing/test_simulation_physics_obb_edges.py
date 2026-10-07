"""OBB edge-edge contact geometry regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    PhysicsMaterial,
    PhysicsSettings,
    PhysicsWorld,
    Quat,
    RigidBody,
    Vec3,
    detect_collision,
)
from skeleton.simulation.physics.collision import (
    _box_box_edge_contact,
    _closest_segment_points,
    _support_edge,
)


def _euler_xyz(x: float, y: float, z: float) -> Quat:
    qx = Quat.from_axis_angle(Vec3.axis(0), x)
    qy = Quat.from_axis_angle(Vec3.axis(1), y)
    qz = Quat.from_axis_angle(Vec3.axis(2), z)
    return (qz * qy * qx).normalized()


def test_closest_segments_cross_at_exact_midpoint() -> None:
    first, second, s, t = _closest_segment_points(
        Vec3(-1.0, 0.0, 0.0),
        Vec3(1.0, 0.0, 0.0),
        Vec3(0.0, -1.0, 0.0),
        Vec3(0.0, 1.0, 0.0),
    )

    assert first.almost_equal(Vec3.zero(), tolerance=1.0e-12)
    assert second.almost_equal(Vec3.zero(), tolerance=1.0e-12)
    assert s == pytest.approx(0.5)
    assert t == pytest.approx(0.5)


def test_closest_segments_clamp_to_finite_endpoints() -> None:
    first, second, s, t = _closest_segment_points(
        Vec3(0.0, 0.0, 0.0),
        Vec3(1.0, 0.0, 0.0),
        Vec3(2.0, 1.0, 0.0),
        Vec3(2.0, 2.0, 0.0),
    )

    assert first == Vec3(1.0, 0.0, 0.0)
    assert second == Vec3(2.0, 1.0, 0.0)
    assert s == pytest.approx(1.0)
    assert t == pytest.approx(0.0)


def test_parallel_segment_solution_is_deterministic_and_finite() -> None:
    left = _closest_segment_points(
        Vec3(-1.0, 0.0, 0.0),
        Vec3(1.0, 0.0, 0.0),
        Vec3(-1.0, 1.0, 0.0),
        Vec3(1.0, 1.0, 0.0),
    )
    right = _closest_segment_points(
        Vec3(-1.0, 0.0, 0.0),
        Vec3(1.0, 0.0, 0.0),
        Vec3(-1.0, 1.0, 0.0),
        Vec3(1.0, 1.0, 0.0),
    )

    assert left == right
    assert left[0] == Vec3(-1.0, 0.0, 0.0)
    assert left[1] == Vec3(-1.0, 1.0, 0.0)
    assert left[2] == pytest.approx(0.0)
    assert left[3] == pytest.approx(0.0)


def test_support_edge_uses_requested_axis_and_extreme_side_topology() -> None:
    shape = BoxShape(Vec3(2.0, 1.0, 0.5))
    body = RigidBody.static(
        "box",
        shape,
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5),
    )
    edge = _support_edge(
        shape,
        body,
        edge_axis_index=0,
        support_direction=Vec3(1.0, 0.0, 1.0),
        label="a",
    )

    assert (edge.end - edge.start).length() == pytest.approx(4.0)
    world_axis = shape.axes(body.transform)[0]
    assert abs((edge.end - edge.start).normalized().dot(world_axis)) > 0.999999
    assert edge.feature_id.startswith("a:edge:0:")


def _edge_edge_pair() -> tuple[RigidBody, RigidBody]:
    half = Vec3(1.5, 0.25, 0.25)
    a = RigidBody.static(
        "a",
        BoxShape(half),
        orientation=_euler_xyz(
            -0.08878234124394857,
            -0.3040513646518991,
            -0.8675054099653075,
        ),
        material=PhysicsMaterial(friction=0.0, restitution=0.0),
    )
    b = RigidBody.dynamic(
        "b",
        BoxShape(half),
        position=Vec3(
            0.6372767520511011,
            -0.6706965645071984,
            0.08683274908525773,
        ),
        orientation=_euler_xyz(
            0.8797484399672191,
            -1.184555870205304,
            0.006676992125300041,
        ),
        material=PhysicsMaterial(friction=0.0, restitution=0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    return a, b


def test_skewed_obb_pair_uses_edge_pair_feature_instead_of_support_corner() -> None:
    a, b = _edge_edge_pair()

    manifold = detect_collision(a, b)

    assert manifold is not None
    assert len(manifold.points) == 1
    point = manifold.points[0]
    assert "edge:" in point.feature_id
    assert "a:edge:0:" in point.feature_id
    assert "b:edge:0:" in point.feature_id
    assert point.penetration > 0.0


def test_edge_contact_point_equals_midpoint_of_selected_closest_edges() -> None:
    a, b = _edge_edge_pair()
    manifold = detect_collision(a, b)
    assert manifold is not None
    point = manifold.points[0]

    edge_a = _support_edge(
        a.shape,
        a,
        edge_axis_index=0,
        support_direction=manifold.normal,
        label="a",
    )
    edge_b = _support_edge(
        b.shape,
        b,
        edge_axis_index=0,
        support_direction=-manifold.normal,
        label="b",
    )
    closest_a, closest_b, _, _ = _closest_segment_points(
        edge_a.start,
        edge_a.end,
        edge_b.start,
        edge_b.end,
    )
    expected = (closest_a + closest_b) * 0.5

    assert point.position.almost_equal(expected, tolerance=1.0e-9)


def test_edge_contact_constructor_is_order_deterministic_for_same_geometry() -> None:
    a, b = _edge_edge_pair()
    manifold = detect_collision(a, b)
    assert manifold is not None

    first = _box_box_edge_contact(
        a,
        b,
        manifold_normal=manifold.normal,
        penetration=manifold.penetration,
        axis_a_index=0,
        axis_b_index=0,
    )
    second = _box_box_edge_contact(
        a,
        b,
        manifold_normal=manifold.normal,
        penetration=manifold.penetration,
        axis_a_index=0,
        axis_b_index=0,
    )

    assert first == second


def test_edge_contact_feature_survives_small_motion_while_topology_is_unchanged() -> None:
    a, b = _edge_edge_pair()
    first = detect_collision(a, b)
    assert first is not None
    assert "edge:" in first.points[0].feature_id

    b.position = b.position + Vec3(1.0e-4, -1.0e-4, 5.0e-5)
    second = detect_collision(a, b)
    assert second is not None
    assert second.points[0].feature_id == first.points[0].feature_id


def test_edge_edge_contact_generates_off_center_angular_response() -> None:
    a, b = _edge_edge_pair()
    b.linear_velocity = Vec3(-2.0, 1.0, 0.5)
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 240.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(a)
    world.add_body(b)

    before = b.angular_velocity
    receipt = world.step()[0]

    assert receipt.manifolds >= 1
    assert b.angular_velocity != before
    assert b.angular_velocity.length() > 0.0
