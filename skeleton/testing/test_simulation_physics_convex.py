"""Finite round-shape and deterministic convex-kernel regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CapsuleShape,
    CylinderShape,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    RigidBody,
    SphereShape,
    Vec3,
    convex_penetration,
    epa_penetration,
    gjk_intersection,
    support_vertex,
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
    )


def test_capsule_support_and_aabb_follow_oriented_segment() -> None:
    shape = CapsuleShape(radius=0.5, half_height=1.0)
    body = _static(
        "capsule",
        shape,
        position=Vec3(2.0, 3.0, 4.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5),
    )

    positive_x = shape.support(Vec3.axis(0), body.transform)
    negative_x = shape.support(-Vec3.axis(0), body.transform)
    bounds = shape.aabb(body.transform)

    assert positive_x.x == pytest.approx(3.5)
    assert negative_x.x == pytest.approx(0.5)
    assert bounds.minimum.x == pytest.approx(0.5)
    assert bounds.maximum.x == pytest.approx(3.5)
    assert bounds.minimum.y == pytest.approx(2.5)
    assert bounds.maximum.y == pytest.approx(3.5)
    assert bounds.minimum.z == pytest.approx(3.5)
    assert bounds.maximum.z == pytest.approx(4.5)


def test_capsule_mass_matches_cylinder_plus_sphere_volume() -> None:
    radius = 0.4
    half_height = 0.75
    density = 2.5
    shape = CapsuleShape(radius, half_height)
    props = shape.mass_properties(density)

    cylinder_volume = math.pi * radius**2 * (2.0 * half_height)
    sphere_volume = (4.0 / 3.0) * math.pi * radius**3
    assert props.mass == pytest.approx(density * (cylinder_volume + sphere_volume))
    assert props.center_of_mass == Vec3.zero()
    assert props.inertia.m00 == pytest.approx(props.inertia.m22)
    assert props.inertia.m00 > 0.0
    assert props.inertia.m11 > 0.0


def test_cylinder_support_aabb_and_principal_inertia_are_analytic() -> None:
    radius = 0.5
    half_height = 1.25
    density = 3.0
    shape = CylinderShape(radius, half_height)
    body = _static("cylinder", shape)

    support = shape.support(Vec3(3.0, 2.0, 4.0), body.transform)
    radial = math.hypot(support.x, support.z)
    props = shape.mass_properties(density)
    length = 2.0 * half_height
    expected_mass = density * math.pi * radius**2 * length

    assert radial == pytest.approx(radius)
    assert support.y == pytest.approx(half_height)
    assert shape.aabb(body.transform).half_extents() == Vec3(radius, half_height, radius)
    assert props.mass == pytest.approx(expected_mass)
    assert props.inertia.m11 == pytest.approx(0.5 * expected_mass * radius**2)
    assert props.inertia.m00 == pytest.approx(
        expected_mass * (3.0 * radius**2 + length**2) / 12.0
    )
    assert props.inertia.m22 == pytest.approx(props.inertia.m00)


def test_cylinder_rotated_aabb_contains_extreme_support_points() -> None:
    shape = CylinderShape(0.4, 1.2)
    body = _static(
        "cylinder",
        shape,
        position=Vec3(1.0, -2.0, 0.5),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.radians(37.0)),
    )
    bounds = shape.aabb(body.transform)

    for direction in (
        Vec3.axis(0),
        -Vec3.axis(0),
        Vec3.axis(1),
        -Vec3.axis(1),
        Vec3.axis(2),
        -Vec3.axis(2),
    ):
        assert bounds.contains(shape.support(direction, body.transform))


def test_capsule_and_cylinder_dimensions_bind_world_configuration_identity() -> None:
    left = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    right = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    left.add_body(_dynamic("shape", CapsuleShape(0.5, 1.0)))
    right.add_body(_dynamic("shape", CapsuleShape(0.5, 1.1)))

    assert left.configuration_digest != right.configuration_digest
    assert left.state_digest != right.state_digest

    cylinder = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    cylinder.add_body(_dynamic("shape", CylinderShape(0.5, 1.0)))
    assert cylinder.configuration_digest != left.configuration_digest


def test_minkowski_support_vertex_binds_both_witnesses() -> None:
    a = _static("a", SphereShape(1.0), Vec3.zero())
    b = _static("b", SphereShape(0.5), Vec3(3.0, 0.0, 0.0))
    vertex = support_vertex(a, b, Vec3.axis(0))

    assert vertex.point_a == Vec3(1.0, 0.0, 0.0)
    assert vertex.point_b == Vec3(2.5, 0.0, 0.0)
    assert vertex.point == Vec3(-1.5, 0.0, 0.0)


def test_gjk_separates_disjoint_spheres() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(3.0, 0.0, 0.0))

    result = gjk_intersection(a, b)

    assert not result.intersects
    assert 1 <= result.iterations <= 64
    assert 1 <= len(result.simplex) <= 4
    assert result.separating_direction.length_squared() > 0.0


def test_gjk_detects_overlapping_spheres_and_boxes() -> None:
    sphere_a = _static("sa", SphereShape(1.0))
    sphere_b = _static("sb", SphereShape(1.0), Vec3(1.5, 0.0, 0.0))
    box_a = _static("ba", BoxShape(Vec3.one()))
    box_b = _static(
        "bb",
        BoxShape(Vec3.one()),
        Vec3(1.4, 0.1, -0.2),
        Quat.from_axis_angle(Vec3.axis(1), math.radians(13.0)),
    )

    sphere_result = gjk_intersection(sphere_a, sphere_b)
    box_result = gjk_intersection(box_a, box_b)

    assert sphere_result.intersects
    assert box_result.intersects
    assert len(sphere_result.simplex) == 4
    assert len(box_result.simplex) == 4


def test_gjk_is_deterministic_for_identical_query() -> None:
    a = _static(
        "a",
        CapsuleShape(0.4, 1.0),
        Vec3(-0.2, 0.1, 0.0),
        Quat.from_axis_angle(Vec3.axis(2), 0.2),
    )
    b = _static(
        "b",
        CylinderShape(0.5, 0.8),
        Vec3(0.4, -0.1, 0.1),
        Quat.from_axis_angle(Vec3.axis(0), -0.3),
    )

    first = gjk_intersection(a, b)
    second = gjk_intersection(a, b)

    assert first == second


def test_gjk_pair_order_preserves_intersection_truth() -> None:
    a = _static("a", CapsuleShape(0.5, 1.0))
    b = _static("b", CylinderShape(0.6, 0.9), Vec3(0.4, 0.0, 0.0))

    forward = gjk_intersection(a, b)
    reverse = gjk_intersection(b, a)

    assert forward.intersects
    assert reverse.intersects
    assert forward.intersects == reverse.intersects


def test_epa_sphere_penetration_recovers_depth_normal_and_witnesses() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(1.5, 0.0, 0.0))
    gjk = gjk_intersection(a, b)
    assert gjk.intersects

    penetration = epa_penetration(
        a,
        b,
        gjk,
        max_iterations=128,
        tolerance=1.0e-5,
    )

    assert penetration is not None
    assert penetration.depth == pytest.approx(0.5, abs=2.0e-3)
    assert penetration.normal.x > 0.995
    assert abs(penetration.normal.y) < 0.05
    assert abs(penetration.normal.z) < 0.05
    assert (penetration.point_a - penetration.point_b).dot(
        penetration.normal
    ) == pytest.approx(penetration.depth, abs=2.0e-3)
    assert penetration.contact_point.almost_equal(
        (penetration.point_a + penetration.point_b) * 0.5,
        tolerance=1.0e-9,
    )


def test_convex_penetration_returns_none_for_separated_shapes() -> None:
    a = _static("a", CapsuleShape(0.5, 1.0))
    b = _static("b", CylinderShape(0.5, 1.0), Vec3(4.0, 0.0, 0.0))

    assert convex_penetration(a, b) is None


def test_convex_penetration_handles_capsule_cylinder_overlap() -> None:
    a = _static(
        "a",
        CapsuleShape(0.5, 1.0),
        Vec3.zero(),
        Quat.from_axis_angle(Vec3.axis(2), 0.15),
    )
    b = _static(
        "b",
        CylinderShape(0.55, 0.9),
        Vec3(0.55, 0.1, 0.0),
        Quat.from_axis_angle(Vec3.axis(0), -0.2),
    )

    penetration = convex_penetration(
        a,
        b,
        epa_iterations=128,
        tolerance=1.0e-5,
    )

    assert penetration is not None
    assert penetration.depth > 0.0
    assert penetration.normal.length() == pytest.approx(1.0)
    assert penetration.iterations <= 128


def test_convex_query_rejects_infinite_plane() -> None:
    plane = _static("plane", PlaneShape())
    sphere = _static("sphere", SphereShape(1.0))

    with pytest.raises(PhysicsValidationError, match="planes"):
        gjk_intersection(plane, sphere)


def test_convex_iteration_and_tolerance_bounds_fail_closed() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(1.0, 0.0, 0.0))

    with pytest.raises(PhysicsValidationError, match="max_iterations"):
        gjk_intersection(a, b, max_iterations=0)
    with pytest.raises(PhysicsValidationError, match="tolerance"):
        gjk_intersection(a, b, tolerance=0.0)
    with pytest.raises(PhysicsValidationError, match="max_iterations"):
        epa_penetration(a, b, max_iterations=0)


def test_convex_query_rejects_same_body_identity() -> None:
    body = _static("same", SphereShape(1.0))
    with pytest.raises(PhysicsValidationError, match="distinct"):
        gjk_intersection(body, body)


def test_epa_rejects_nonintersecting_or_wrong_result_contract() -> None:
    a = _static("a", SphereShape(1.0))
    b = _static("b", SphereShape(1.0), Vec3(3.0, 0.0, 0.0))
    separated = gjk_intersection(a, b)

    assert epa_penetration(a, b, separated) is None
    with pytest.raises(PhysicsValidationError, match="GJKResult"):
        epa_penetration(a, b, "bad")  # type: ignore[arg-type]
