"""Capsule/triangle closest geometry and capsule-mesh contact regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    CapsuleShape,
    PhysicsSettings,
    PhysicsWorld,
    Quat,
    RigidBody,
    TriangleMeshShape,
    Vec3,
    detect_collision,
)
from skeleton.simulation.physics.mesh import closest_points_segment_triangle


def _floor_mesh() -> TriangleMeshShape:
    return TriangleMeshShape(
        (
            Vec3(-2.0, 0.0, -2.0),
            Vec3(2.0, 0.0, -2.0),
            Vec3(2.0, 0.0, 2.0),
            Vec3(-2.0, 0.0, 2.0),
        ),
        ((0, 2, 1), (0, 3, 2)),
    )


def test_segment_triangle_intersection_returns_zero_distance() -> None:
    result = closest_points_segment_triangle(
        Vec3(0.0, 1.0, 0.0),
        Vec3(0.0, -1.0, 0.0),
        Vec3(-1.0, 0.0, -1.0),
        Vec3(1.0, 0.0, -1.0),
        Vec3(0.0, 0.0, 1.0),
    )

    assert result.distance_squared == pytest.approx(0.0)
    assert result.segment_point == result.triangle_point
    assert result.segment_parameter == pytest.approx(0.5)
    assert sum(result.barycentric) == pytest.approx(1.0)


def test_segment_triangle_face_distance_uses_segment_endpoint_projection() -> None:
    result = closest_points_segment_triangle(
        Vec3(0.0, 1.0, 0.0),
        Vec3(0.0, 2.0, 0.0),
        Vec3(-2.0, 0.0, -2.0),
        Vec3(2.0, 0.0, -2.0),
        Vec3(0.0, 0.0, 2.0),
    )

    assert result.segment_point == Vec3(0.0, 1.0, 0.0)
    assert result.triangle_point == Vec3.zero()
    assert result.distance_squared == pytest.approx(1.0)


def test_segment_triangle_edge_distance_uses_interior_segment_point() -> None:
    result = closest_points_segment_triangle(
        Vec3(2.0, -1.0, 0.0),
        Vec3(2.0, 1.0, 0.0),
        Vec3(-1.0, 0.0, -1.0),
        Vec3(1.0, 0.0, -1.0),
        Vec3(1.0, 0.0, 1.0),
    )

    assert result.segment_parameter == pytest.approx(0.5)
    assert result.segment_point == Vec3(2.0, 0.0, 0.0)
    assert result.triangle_point.x == pytest.approx(1.0)
    assert result.triangle_point.y == pytest.approx(0.0)
    assert result.distance_squared == pytest.approx(1.0)


def test_segment_triangle_vertex_distance_is_deterministic() -> None:
    args = (
        Vec3(2.0, 1.0, 2.0),
        Vec3(2.0, 2.0, 2.0),
        Vec3.zero(),
        Vec3.axis(0),
        Vec3.axis(2),
    )
    first = closest_points_segment_triangle(*args)
    second = closest_points_segment_triangle(*args)

    assert first == second
    assert first.triangle_point == Vec3(0.5, 0.0, 0.5)
    assert first.segment_parameter == pytest.approx(0.0)


def test_capsule_above_mesh_gets_upward_contact() -> None:
    mesh = RigidBody.static("mesh", _floor_mesh())
    capsule = RigidBody.dynamic(
        "capsule",
        CapsuleShape(0.4, 0.8),
        position=Vec3(0.0, 1.1, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )

    manifold = detect_collision(mesh, capsule)

    assert manifold is not None
    assert manifold.normal.y > 0.999999
    assert manifold.penetration == pytest.approx(0.1, abs=1.0e-8)
    assert manifold.points[0].feature_id.startswith("mesh-capsule:t")


def test_capsule_below_mesh_gets_downward_contact() -> None:
    mesh = RigidBody.static("mesh", _floor_mesh())
    capsule = RigidBody.dynamic(
        "capsule",
        CapsuleShape(0.4, 0.8),
        position=Vec3(0.0, -1.1, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )

    manifold = detect_collision(mesh, capsule)

    assert manifold is not None
    assert manifold.normal.y < -0.999999
    assert manifold.penetration == pytest.approx(0.1, abs=1.0e-8)


def test_capsule_mesh_pair_reversal_flips_normal() -> None:
    mesh = RigidBody.static("mesh", _floor_mesh())
    capsule = RigidBody.dynamic(
        "capsule",
        CapsuleShape(0.4, 0.8),
        position=Vec3(0.2, 1.1, 0.1),
    )

    forward = detect_collision(mesh, capsule)
    reverse = detect_collision(capsule, mesh)

    assert forward is not None
    assert reverse is not None
    assert reverse.normal == -forward.normal
    assert reverse.points == forward.points


def test_rotated_capsule_uses_actual_center_segment_against_mesh() -> None:
    mesh = RigidBody.static("mesh", _floor_mesh())
    capsule = RigidBody.dynamic(
        "capsule",
        CapsuleShape(0.3, 1.0),
        position=Vec3(0.0, 0.25, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5),
        linear_damping=0.0,
        angular_damping=0.0,
    )

    manifold = detect_collision(mesh, capsule)

    assert manifold is not None
    assert manifold.normal.y > 0.999999
    assert manifold.penetration == pytest.approx(0.05, abs=1.0e-8)


def test_world_solver_resolves_capsule_against_mesh_floor() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(RigidBody.static("mesh", _floor_mesh()))
    capsule = RigidBody.dynamic(
        "capsule",
        CapsuleShape(0.4, 0.8),
        position=Vec3(0.0, 1.1, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    capsule.linear_velocity = Vec3(0.0, -2.0, 0.0)
    world.add_body(capsule)

    receipt = world.step()[0]

    assert receipt.manifolds == 1
    assert receipt.solver.normal_impulses > 0
    assert capsule.linear_velocity.y > -2.0
