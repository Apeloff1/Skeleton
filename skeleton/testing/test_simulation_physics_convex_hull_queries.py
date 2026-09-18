"""Exact convex-hull raycast and sphere-cast regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    ConvexHullShape,
    PhysicsSettings,
    PhysicsWorld,
    Quat,
    Ray,
    RigidBody,
    SphereShape,
    Vec3,
    raycast_body,
    sphere_cast_body,
)


def _cube_hull(half: float = 1.0) -> ConvexHullShape:
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
        (0, 2, 1),
        (0, 3, 2),
        (4, 5, 6),
        (4, 6, 7),
        (0, 1, 5),
        (0, 5, 4),
        (3, 7, 6),
        (3, 6, 2),
        (0, 4, 7),
        (0, 7, 3),
        (1, 2, 6),
        (1, 6, 5),
    )
    return ConvexHullShape(vertices, faces)


def _hull_body(
    body_id: str = "hull",
    *,
    position: Vec3 = Vec3(),
    orientation: Quat = Quat.identity(),
) -> RigidBody:
    return RigidBody.static(
        body_id,
        _cube_hull(),
        position=position,
        orientation=orientation,
    )


def test_hull_raycast_hits_exact_axis_face() -> None:
    hull = _hull_body()
    ray = Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0)

    hit = raycast_body(ray, hull)

    assert hit is not None
    assert hit.body_id == "hull"
    assert hit.distance == pytest.approx(2.0, abs=1.0e-10)
    assert hit.point == Vec3(-1.0, 0.0, 0.0)
    assert hit.normal == -Vec3.axis(0)


def test_hull_raycast_from_inside_returns_zero_and_opposes_travel() -> None:
    hull = _hull_body()
    direction = Vec3(1.0, 2.0, -0.5).normalized()
    ray = Ray(Vec3.zero(), direction, 10.0)

    hit = raycast_body(ray, hull)

    assert hit is not None
    assert hit.distance == 0.0
    assert hit.point == Vec3.zero()
    assert hit.normal.almost_equal(-direction, tolerance=1.0e-12)


def test_hull_raycast_parallel_outside_face_misses() -> None:
    hull = _hull_body()
    ray = Ray(Vec3(-3.0, 1.1, 0.0), Vec3.axis(0), 10.0)

    assert raycast_body(ray, hull) is None


def test_hull_raycast_corner_clearance_misses() -> None:
    hull = _hull_body()
    ray = Ray(Vec3(-3.0, 1.01, 1.01), Vec3.axis(0), 10.0)

    assert raycast_body(ray, hull) is None


def test_rotated_hull_raycast_uses_world_face_normal() -> None:
    hull = _hull_body(
        position=Vec3(3.0, 0.0, 0.0),
        orientation=Quat.from_axis_angle(
            Vec3.axis(2),
            math.pi * 0.25,
        ),
    )
    ray = Ray(Vec3.zero(), Vec3.axis(0), 10.0)

    hit = raycast_body(ray, hull)

    assert hit is not None
    expected_distance = 3.0 - math.sqrt(2.0)
    assert hit.distance == pytest.approx(expected_distance, abs=2.0e-9)
    assert hit.normal.x < -0.7
    assert abs(hit.normal.length() - 1.0) < 1.0e-12


def test_hull_raycast_respects_max_distance() -> None:
    hull = _hull_body(position=Vec3(5.0, 0.0, 0.0))
    ray = Ray(Vec3.zero(), Vec3.axis(0), 3.0)

    assert raycast_body(ray, hull) is None


def test_hull_sphere_cast_matches_exact_axis_expansion() -> None:
    hull = _hull_body()
    ray = Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0)

    hit = sphere_cast_body(ray, 0.5, hull)

    assert hit is not None
    assert hit.distance == pytest.approx(1.5, abs=4.0e-6)
    assert hit.point.x == pytest.approx(-1.5, abs=4.0e-6)
    assert hit.normal.x < -0.999


def test_hull_sphere_cast_rejects_rounded_corner_false_positive() -> None:
    hull = _hull_body()
    ray = Ray(
        Vec3(-3.0, 1.09, 1.09),
        Vec3.axis(0),
        6.0,
    )

    hit = sphere_cast_body(ray, 0.1, hull)

    assert hit is None


def test_hull_sphere_cast_hits_true_rounded_corner() -> None:
    hull = _hull_body()
    ray = Ray(
        Vec3(-3.0, 1.05, 1.05),
        Vec3.axis(0),
        6.0,
    )

    hit = sphere_cast_body(ray, 0.1, hull)

    assert hit is not None
    assert 1.9 < hit.distance < 2.1
    assert hit.normal.x < 0.0
    assert hit.normal.y > 0.0
    assert hit.normal.z > 0.0


def test_hull_sphere_cast_from_overlap_returns_zero() -> None:
    hull = _hull_body()
    ray = Ray(Vec3.zero(), Vec3.axis(0), 10.0)

    hit = sphere_cast_body(ray, 0.2, hull)

    assert hit is not None
    assert hit.distance == 0.0


def test_hull_sphere_cast_uses_current_transform_not_target_velocity() -> None:
    static_hull = _hull_body("static")
    moving_hull = RigidBody.kinematic(
        "moving",
        _cube_hull(),
        linear_velocity=Vec3(100.0, -50.0, 20.0),
        angular_velocity=Vec3(3.0, 2.0, 1.0),
    )
    ray = Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0)

    static_hit = sphere_cast_body(ray, 0.25, static_hull)
    moving_hit = sphere_cast_body(ray, 0.25, moving_hull)

    assert static_hit is not None
    assert moving_hit is not None
    assert moving_hit.distance == pytest.approx(
        static_hit.distance,
        abs=1.0e-8,
    )
    assert moving_hit.point.almost_equal(
        static_hit.point,
        tolerance=1.0e-8,
    )
    assert moving_hit.normal.almost_equal(
        static_hit.normal,
        tolerance=1.0e-8,
    )


def test_world_raycast_orders_hull_and_sphere_by_distance() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    world.add_body(
        _hull_body(
            "far-hull",
            position=Vec3(5.0, 0.0, 0.0),
        )
    )
    world.add_body(
        RigidBody.static(
            "near-sphere",
            SphereShape(0.5),
            position=Vec3(2.0, 0.0, 0.0),
        )
    )

    hits = world.raycast(
        Ray(Vec3.zero(), Vec3.axis(0), 10.0)
    )

    assert tuple(hit.body_id for hit in hits) == (
        "near-sphere",
        "far-hull",
    )
    assert hits[0].distance == pytest.approx(1.5)
    assert hits[1].distance == pytest.approx(4.0)


def test_world_sphere_cast_includes_convex_hull() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    world.add_body(
        _hull_body(
            "hull",
            position=Vec3(5.0, 0.0, 0.0),
        )
    )

    hits = world.sphere_cast(
        Ray(Vec3.zero(), Vec3.axis(0), 10.0),
        0.5,
    )

    assert len(hits) == 1
    assert hits[0].body_id == "hull"
    assert hits[0].distance == pytest.approx(3.5, abs=5.0e-6)


def test_hull_queries_are_deterministic_under_repeated_calls() -> None:
    hull = _hull_body(
        position=Vec3(2.0, 0.1, -0.2),
        orientation=Quat.from_axis_angle(Vec3.axis(1), 0.23),
    )
    ray = Ray(
        Vec3(-4.0, 0.2, -0.1),
        Vec3(1.0, -0.02, 0.03),
        12.0,
    )

    assert raycast_body(ray, hull) == raycast_body(ray, hull)
    assert sphere_cast_body(ray, 0.2, hull) == sphere_cast_body(
        ray,
        0.2,
        hull,
    )
