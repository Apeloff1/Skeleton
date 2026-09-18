"""Convex hull topology, mass, GJK distance, and collision regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CapsuleShape,
    ConvexHullShape,
    CylinderShape,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    SphereShape,
    Vec3,
    detect_collision,
    gjk_distance,
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


def _static(body_id: str, shape, position: Vec3 = Vec3()) -> RigidBody:
    return RigidBody.static(body_id, shape, position=position)


def _dynamic(body_id: str, shape, position: Vec3 = Vec3()) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        shape,
        position=position,
        linear_damping=0.0,
        angular_damping=0.0,
    )


def test_cube_hull_support_matches_extreme_vertex() -> None:
    hull = _cube_hull()
    body = _static("hull", hull, Vec3(2.0, 3.0, 4.0))

    support = hull.support(Vec3(1.0, -2.0, 3.0), body.transform)

    assert support == Vec3(3.0, 2.0, 5.0)
    bounds = hull.aabb(body.transform)
    assert bounds.minimum == Vec3(1.0, 2.0, 3.0)
    assert bounds.maximum == Vec3(3.0, 4.0, 5.0)


def test_cube_hull_mass_properties_match_analytic_box() -> None:
    density = 2.5
    hull = _cube_hull(1.0)
    box = BoxShape(Vec3.one())

    hull_props = hull.mass_properties(density)
    box_props = box.mass_properties(density)

    assert hull_props.mass == pytest.approx(box_props.mass, rel=1.0e-10)
    assert hull_props.center_of_mass.almost_equal(
        Vec3.zero(),
        tolerance=1.0e-12,
    )
    assert hull_props.inertia.m00 == pytest.approx(box_props.inertia.m00, rel=1.0e-9)
    assert hull_props.inertia.m11 == pytest.approx(box_props.inertia.m11, rel=1.0e-9)
    assert hull_props.inertia.m22 == pytest.approx(box_props.inertia.m22, rel=1.0e-9)
    assert hull_props.inertia.m01 == pytest.approx(0.0, abs=1.0e-10)
    assert hull_props.inertia.m02 == pytest.approx(0.0, abs=1.0e-10)
    assert hull_props.inertia.m12 == pytest.approx(0.0, abs=1.0e-10)


def test_reversing_all_hull_faces_preserves_mass_properties() -> None:
    hull = _cube_hull()
    reversed_hull = ConvexHullShape(
        hull.vertices,
        tuple((face[0], face[2], face[1]) for face in hull.faces),
    )

    left = hull.mass_properties(1.0)
    right = reversed_hull.mass_properties(1.0)

    assert right.mass == pytest.approx(left.mass)
    assert right.center_of_mass.almost_equal(left.center_of_mass, tolerance=1.0e-12)
    assert right.inertia.to_tuple() == pytest.approx(left.inertia.to_tuple())


def test_hull_rejects_open_surface() -> None:
    hull = _cube_hull()
    with pytest.raises(PhysicsValidationError, match="closed"):
        ConvexHullShape(hull.vertices, hull.faces[:-1])


def test_hull_rejects_inconsistent_edge_winding() -> None:
    hull = _cube_hull()
    bad = list(hull.faces)
    face = bad[0]
    bad[0] = (face[0], face[2], face[1])
    with pytest.raises(PhysicsValidationError, match="winding"):
        ConvexHullShape(hull.vertices, tuple(bad))


def test_hull_rejects_nonconvex_face_vertex_relation() -> None:
    hull = _cube_hull()
    vertices = list(hull.vertices)
    vertices[6] = Vec3(0.0, 0.0, 0.0)
    with pytest.raises(PhysicsValidationError):
        ConvexHullShape(tuple(vertices), hull.faces)


def test_centered_hull_can_create_dynamic_rigid_body() -> None:
    body = _dynamic("hull", _cube_hull())
    assert body.mass > 0.0
    assert body.local_inertia.is_invertible()


def test_offset_hull_fails_existing_dynamic_center_of_mass_contract() -> None:
    hull = _cube_hull()
    shifted = ConvexHullShape(
        tuple(vertex + Vec3(1.0, 0.0, 0.0) for vertex in hull.vertices),
        hull.faces,
    )
    with pytest.raises(PhysicsValidationError, match="offset centers"):
        _dynamic("shifted", shifted)


def test_hull_topology_binds_world_configuration_identity() -> None:
    left = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    right = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    left.add_body(_dynamic("hull", _cube_hull(1.0)))
    right.add_body(_dynamic("hull", _cube_hull(1.1)))

    assert left.configuration_digest != right.configuration_digest
    assert left.state_digest != right.state_digest


def test_gjk_distance_sphere_sphere_exact_witnesses() -> None:
    a = _static("a", SphereShape(1.0), Vec3.zero())
    b = _static("b", SphereShape(1.0), Vec3(3.0, 0.0, 0.0))

    result = gjk_distance(a, b)

    assert not result.intersects
    assert result.distance == pytest.approx(1.0, abs=1.0e-9)
    assert result.normal == Vec3.axis(0)
    assert result.point_a.almost_equal(Vec3(1.0, 0.0, 0.0), tolerance=1.0e-9)
    assert result.point_b.almost_equal(Vec3(2.0, 0.0, 0.0), tolerance=1.0e-9)
    assert (result.point_b - result.point_a).length() == pytest.approx(result.distance)


def test_gjk_distance_pair_reversal_swaps_witnesses_and_flips_normal() -> None:
    a = _static("a", CapsuleShape(0.5, 0.8), Vec3(-2.0, 0.0, 0.0))
    b = _static("b", CylinderShape(0.5, 0.8), Vec3(2.0, 0.0, 0.0))

    forward = gjk_distance(a, b)
    reverse = gjk_distance(b, a)

    assert forward.distance == pytest.approx(reverse.distance, rel=1.0e-8)
    assert forward.point_a.almost_equal(reverse.point_b, tolerance=1.0e-8)
    assert forward.point_b.almost_equal(reverse.point_a, tolerance=1.0e-8)
    assert forward.normal.dot(reverse.normal) < -0.999999


def test_gjk_distance_hull_sphere_matches_axis_gap() -> None:
    hull = _static("hull", _cube_hull(), Vec3.zero())
    sphere = _static("sphere", SphereShape(0.5), Vec3(3.0, 0.0, 0.0))

    result = gjk_distance(hull, sphere)

    assert not result.intersects
    assert result.distance == pytest.approx(1.5, abs=1.0e-8)
    assert result.normal.x > 0.999999
    assert result.point_a.x == pytest.approx(1.0, abs=1.0e-8)
    assert result.point_b.x == pytest.approx(2.5, abs=1.0e-8)


def test_gjk_distance_returns_zero_for_overlap() -> None:
    a = _static("a", _cube_hull())
    b = _static("b", SphereShape(0.75), Vec3(0.5, 0.0, 0.0))

    result = gjk_distance(a, b)

    assert result.intersects
    assert result.distance == pytest.approx(0.0)
    assert result.normal == Vec3.zero()


def test_gjk_distance_is_deterministic() -> None:
    a = _static("a", _cube_hull(), Vec3(-1.7, 0.2, 0.1))
    b = _static("b", CylinderShape(0.4, 0.9), Vec3(1.9, -0.1, 0.3))

    first = gjk_distance(a, b)
    second = gjk_distance(a, b)

    assert first == second


def test_hull_hull_collision_uses_generic_convex_kernel() -> None:
    a = _static("a", _cube_hull())
    b = _dynamic("b", _cube_hull(), Vec3(1.5, 0.0, 0.0))

    manifold = detect_collision(a, b)

    assert manifold is not None
    assert manifold.penetration > 0.0
    assert manifold.points[0].feature_id.startswith("convex:convex_hull")
    assert manifold.normal.x > 0.9


def test_plane_hull_contact_uses_deepest_support() -> None:
    plane = _static("ground", PlaneShape())
    hull = _dynamic("hull", _cube_hull(), Vec3(0.0, 0.8, 0.0))

    manifold = detect_collision(plane, hull)

    assert manifold is not None
    assert manifold.penetration == pytest.approx(0.2, abs=1.0e-7)
    assert manifold.normal == Vec3.axis(1)
    assert manifold.points[0].feature_id == "plane-convex_hull:support"


def test_world_solver_resolves_dynamic_hull_against_plane() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static("ground", PlaneShape()))
    hull = _dynamic("hull", _cube_hull(), Vec3(0.0, 0.8, 0.0))
    hull.linear_velocity = Vec3(0.0, -1.0, 0.0)
    world.add_body(hull)

    receipt = world.step()[0]

    assert receipt.manifolds == 1
    assert receipt.solver.normal_impulses > 0
    assert hull.linear_velocity.y > -1.0
