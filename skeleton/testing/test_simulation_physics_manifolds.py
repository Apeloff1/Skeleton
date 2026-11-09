"""Geometric manifold quality and persistence regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    ContactManifold,
    ContactPoint,
    PhysicsMaterial,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    RigidBody,
    Vec3,
    detect_collision,
)


def _box(
    body_id: str,
    *,
    position: Vec3 = Vec3(),
    half: Vec3 = Vec3(0.5, 0.5, 0.5),
    orientation: Quat = Quat.identity(),
    static: bool = False,
) -> RigidBody:
    factory = RigidBody.static if static else RigidBody.dynamic
    return factory(
        body_id,
        BoxShape(half),
        position=position,
        orientation=orientation,
        material=PhysicsMaterial(friction=0.8, restitution=0.0),
        **(
            {}
            if static
            else {
                "linear_damping": 0.0,
                "angular_damping": 0.0,
            }
        ),
    )


def test_plane_box_face_contact_emits_four_geometric_points() -> None:
    plane = RigidBody.static("ground", PlaneShape())
    box = _box("box", position=Vec3(0.0, 0.5, 0.0))

    manifold = detect_collision(plane, box)
    assert manifold is not None
    assert manifold.normal == Vec3.axis(1)
    assert len(manifold.points) == 4
    assert len({point.feature_id for point in manifold.points}) == 4
    assert {point.feature_id for point in manifold.points} == {
        "plane-box:v0",
        "plane-box:v1",
        "plane-box:v4",
        "plane-box:v5",
    }
    assert all(point.penetration == pytest.approx(0.0) for point in manifold.points)
    assert all(point.position.y == pytest.approx(0.0) for point in manifold.points)


def test_plane_box_penetration_tracks_each_vertex_independently() -> None:
    plane = RigidBody.static("ground", PlaneShape())
    box = _box(
        "box",
        position=Vec3(0.0, 0.4, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.radians(10.0)),
    )

    manifold = detect_collision(plane, box)
    assert manifold is not None
    assert 1 <= len(manifold.points) <= 4
    assert all(point.penetration >= 0.0 for point in manifold.points)
    assert max(point.penetration for point in manifold.points) > 0.0
    assert len({point.feature_id for point in manifold.points}) == len(manifold.points)


def test_plane_box_deep_overlap_is_reduced_to_hard_four_point_bound() -> None:
    plane = RigidBody.static("ground", PlaneShape())
    box = _box("box", position=Vec3(0.0, -2.0, 0.0))

    manifold = detect_collision(plane, box)
    assert manifold is not None
    assert len(manifold.points) == 4
    assert len({point.feature_id for point in manifold.points}) == 4


def test_aligned_box_face_contact_emits_four_clipped_points() -> None:
    left = _box("a", position=Vec3(0.0, 0.0, 0.0), static=True)
    right = _box("b", position=Vec3(0.9, 0.0, 0.0))

    manifold = detect_collision(left, right)
    assert manifold is not None
    assert manifold.normal.x > 0.999999
    assert len(manifold.points) == 4
    assert len({point.feature_id for point in manifold.points}) == 4
    assert all(point.penetration == pytest.approx(0.1) for point in manifold.points)
    assert all("box-box:" in point.feature_id for point in manifold.points)


def test_box_face_manifold_is_deterministic_for_identical_geometry() -> None:
    left = _box(
        "a",
        position=Vec3(-0.1, 0.0, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(1), math.radians(7.0)),
        static=True,
    )
    right = _box(
        "b",
        position=Vec3(0.78, 0.05, 0.04),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.radians(-4.0)),
    )

    first = detect_collision(left, right)
    second = detect_collision(left, right)
    assert first is not None
    assert second is not None
    assert first == second
    assert tuple(point.feature_id for point in first.points) == tuple(
        sorted(point.feature_id for point in first.points)
    )


def test_box_face_features_survive_small_in_face_translation_when_topology_stable() -> None:
    left = _box(
        "a",
        position=Vec3.zero(),
        half=Vec3(0.5, 1.0, 1.0),
        static=True,
    )
    right = _box(
        "b",
        position=Vec3(0.9, 0.0, 0.0),
        half=Vec3(0.5, 0.4, 0.4),
    )
    first = detect_collision(left, right)
    assert first is not None
    assert len(first.points) == 4

    right.position = Vec3(0.9, 0.02, 0.01)
    second = detect_collision(left, right)
    assert second is not None
    assert len(second.points) == 4

    first_features = {point.feature_id for point in first.points}
    second_features = {point.feature_id for point in second.points}
    assert second_features == first_features


def test_rotated_face_contact_remains_bounded_and_unique() -> None:
    left = _box(
        "a",
        position=Vec3.zero(),
        half=Vec3(1.0, 0.6, 0.8),
        orientation=Quat.from_axis_angle(Vec3.axis(1), math.radians(17.0)),
        static=True,
    )
    right = _box(
        "b",
        position=Vec3(1.35, 0.08, 0.02),
        half=Vec3(0.7, 0.7, 0.7),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.radians(11.0)),
    )
    manifold = detect_collision(left, right)
    assert manifold is not None
    assert 1 <= len(manifold.points) <= 4
    assert len({point.feature_id for point in manifold.points}) == len(manifold.points)
    assert all(len(point.feature_id) <= 128 for point in manifold.points)


def test_contact_manifold_rejects_duplicate_feature_identity() -> None:
    material = PhysicsMaterial()
    from skeleton.simulation.physics import combine_materials

    contact_material = combine_materials(material, material)
    with pytest.raises(PhysicsValidationError, match="feature ids"):
        ContactManifold(
            "a",
            "b",
            Vec3.axis(1),
            (
                ContactPoint(Vec3.zero(), 0.1, "duplicate"),
                ContactPoint(Vec3.axis(0), 0.1, "duplicate"),
            ),
            contact_material,
        )


def test_contact_manifold_rejects_more_than_four_points() -> None:
    material = PhysicsMaterial()
    from skeleton.simulation.physics import combine_materials

    contact_material = combine_materials(material, material)
    points = tuple(
        ContactPoint(Vec3(float(index), 0.0, 0.0), 0.0, f"p{index}")
        for index in range(5)
    )
    with pytest.raises(PhysicsValidationError, match="point bound"):
        ContactManifold("a", "b", Vec3.axis(1), points, contact_material)


def test_resting_box_warm_starts_multiple_independent_contact_features() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            fixed_dt=1.0 / 120.0,
            velocity_iterations=8,
            position_iterations=4,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    box = _box("box", position=Vec3(0.0, 0.5, 0.0))
    world.add_body(box)

    first = world.step()[0]
    assert first.contact_points == 4
    assert first.solver.cached_contacts == 4
    assert world.contact_cache_size() == 4

    second = world.step()[0]
    assert second.contact_points == 4
    assert second.solver.warm_started_contacts >= 2
    assert second.solver.cached_contacts == 4


def test_symmetric_resting_box_does_not_gain_spurious_spin_from_single_point_bias() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            fixed_dt=1.0 / 240.0,
            velocity_iterations=12,
            position_iterations=6,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    box = _box("box", position=Vec3(0.0, 0.5005, 0.0))
    world.add_body(box)

    world.step(240)

    assert abs(box.angular_velocity.x) < 1.0e-5
    assert abs(box.angular_velocity.z) < 1.0e-5
    assert box.position.y > 0.49
