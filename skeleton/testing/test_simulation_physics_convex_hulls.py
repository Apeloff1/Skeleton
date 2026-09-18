"""Canonical convex-hull topology, mass, query, collision, and CCD regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    ConvexHullShape,
    ContinuousCollisionDetector,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    Ray,
    RigidBody,
    SphereShape,
    Vec3,
    detect_collision,
    raycast_body,
    sphere_cast_body,
)


def _cube_vertices(half: float = 1.0) -> tuple[Vec3, ...]:
    h = half
    return (
        Vec3(-h, -h, -h),
        Vec3(-h, -h, h),
        Vec3(-h, h, -h),
        Vec3(-h, h, h),
        Vec3(h, -h, -h),
        Vec3(h, -h, h),
        Vec3(h, h, -h),
        Vec3(h, h, h),
    )


def _cube_triangles() -> tuple[tuple[int, int, int], ...]:
    # Consistently outward winding for the vertex order above.
    return (
        (0, 3, 2),
        (0, 1, 3),
        (4, 6, 7),
        (4, 7, 5),
        (0, 4, 5),
        (0, 5, 1),
        (2, 3, 7),
        (2, 7, 6),
        (0, 2, 6),
        (0, 6, 4),
        (1, 5, 7),
        (1, 7, 3),
    )


def _cube(half: float = 1.0) -> ConvexHullShape:
    return ConvexHullShape(_cube_vertices(half), _cube_triangles())


def _permuted_cube() -> ConvexHullShape:
    vertices = _cube_vertices()
    triangles = _cube_triangles()
    permutation = (7, 2, 5, 0, 6, 1, 4, 3)
    old_to_new = {
        old: new
        for new, old in enumerate(permutation)
    }
    permuted_vertices = tuple(vertices[index] for index in permutation)
    permuted_triangles = []
    for triangle in reversed(triangles):
        mapped = tuple(old_to_new[index] for index in triangle)
        # Cyclic rotation preserves winding but changes source representation.
        permuted_triangles.append((mapped[1], mapped[2], mapped[0]))
    return ConvexHullShape(
        permuted_vertices,
        tuple(permuted_triangles),
    )


def _static(
    body_id: str,
    shape,
    position: Vec3 = Vec3(),
    orientation: Quat = Quat.identity(),
) -> RigidBody:
    return RigidBody.static(
        body_id,
        shape,
        position=position,
        orientation=orientation,
    )


def _dynamic(
    body_id: str,
    shape,
    position: Vec3 = Vec3(),
    orientation: Quat = Quat.identity(),
    *,
    continuous: bool = False,
) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        shape,
        position=position,
        orientation=orientation,
        continuous=continuous,
        linear_damping=0.0,
        angular_damping=0.0,
    )


def test_convex_hull_canonicalization_is_input_order_invariant() -> None:
    canonical = _cube()
    permuted = _permuted_cube()

    assert canonical == permuted
    assert canonical.vertices == tuple(
        sorted(canonical.vertices, key=lambda row: row.to_tuple())
    )
    assert canonical.triangles == tuple(sorted(canonical.triangles))


def test_convex_hull_accepts_globally_reversed_winding_and_canonicalizes_outward() -> None:
    triangles = tuple(
        (a, c, b)
        for a, b, c in _cube_triangles()
    )
    hull = ConvexHullShape(_cube_vertices(), triangles)

    assert hull == _cube()


def test_convex_hull_cube_mass_center_and_inertia_are_exact() -> None:
    hull = _cube()
    props = hull.mass_properties(1.0)

    assert props.mass == pytest.approx(8.0, abs=1.0e-12)
    assert props.center_of_mass.almost_equal(Vec3.zero(), tolerance=1.0e-12)
    expected = 16.0 / 3.0
    assert props.inertia.m00 == pytest.approx(expected, abs=1.0e-11)
    assert props.inertia.m11 == pytest.approx(expected, abs=1.0e-11)
    assert props.inertia.m22 == pytest.approx(expected, abs=1.0e-11)
    assert props.inertia.m01 == pytest.approx(0.0, abs=1.0e-11)
    assert props.inertia.m02 == pytest.approx(0.0, abs=1.0e-11)
    assert props.inertia.m12 == pytest.approx(0.0, abs=1.0e-11)


def test_centered_convex_hull_can_construct_dynamic_body() -> None:
    body = _dynamic("hull", _cube(0.5))

    assert body.mass == pytest.approx(1.0)
    assert body.local_inertia.is_invertible()


def test_off_center_convex_hull_dynamic_body_requires_future_compound_com_support() -> None:
    vertices = tuple(
        vertex + Vec3(2.0, 0.0, 0.0)
        for vertex in _cube_vertices(0.5)
    )
    hull = ConvexHullShape(vertices, _cube_triangles())

    with pytest.raises(PhysicsValidationError, match="offset centers"):
        _dynamic("offset", hull)


def test_convex_hull_support_and_aabb_follow_transform() -> None:
    hull = _cube(0.5)
    body = _static(
        "hull",
        hull,
        position=Vec3(2.0, 3.0, -1.0),
        orientation=Quat.from_axis_angle(
            Vec3.axis(2),
            math.pi * 0.5,
        ),
    )

    support = hull.support(Vec3.axis(0), body.transform)
    bounds = hull.aabb(body.transform)

    assert support.x == pytest.approx(2.5)
    assert bounds.minimum.almost_equal(
        Vec3(1.5, 2.5, -1.5),
        tolerance=1.0e-12,
    )
    assert bounds.maximum.almost_equal(
        Vec3(2.5, 3.5, -0.5),
        tolerance=1.0e-12,
    )
    assert hull.bounding_radius() == pytest.approx(math.sqrt(0.75))


def test_convex_hull_world_identity_is_permutation_invariant_but_topology_bound() -> None:
    left = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    right = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    left.add_body(_static("hull", _cube()))
    right.add_body(_static("hull", _permuted_cube()))

    assert left.configuration_digest == right.configuration_digest
    assert left.state_digest == right.state_digest

    alternate = list(_cube_triangles())
    # Flip both triangles on +Z to use the opposite diagonal while preserving
    # the same cube surface and outward winding.
    alternate[-2:] = [(1, 5, 3), (3, 5, 7)]
    other = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    other.add_body(
        _static(
            "hull",
            ConvexHullShape(_cube_vertices(), tuple(alternate)),
        )
    )
    assert other.configuration_digest != left.configuration_digest


def test_convex_hull_rejects_duplicate_vertices() -> None:
    vertices = list(_cube_vertices())
    vertices[-1] = vertices[0]
    with pytest.raises(PhysicsValidationError, match="unique"):
        ConvexHullShape(tuple(vertices), _cube_triangles())


def test_convex_hull_rejects_open_mesh() -> None:
    with pytest.raises(PhysicsValidationError, match="closed"):
        ConvexHullShape(
            _cube_vertices(),
            _cube_triangles()[:-1],
        )


def test_convex_hull_rejects_inconsistent_face_winding() -> None:
    triangles = list(_cube_triangles())
    a, b, c = triangles[0]
    triangles[0] = (a, c, b)

    with pytest.raises(PhysicsValidationError, match="winding"):
        ConvexHullShape(_cube_vertices(), tuple(triangles))


def test_convex_hull_rejects_repeated_triangle_indices() -> None:
    triangles = list(_cube_triangles())
    triangles[0] = (0, 0, 1)

    with pytest.raises(PhysicsValidationError, match="distinct"):
        ConvexHullShape(_cube_vertices(), tuple(triangles))


def test_convex_hull_rejects_nonconvex_closed_mesh() -> None:
    vertices = list(_cube_vertices())
    vertices[7] = Vec3(0.2, 0.2, 0.2)

    with pytest.raises(PhysicsValidationError, match="not convex"):
        ConvexHullShape(tuple(vertices), _cube_triangles())


def test_convex_hull_sphere_contact_uses_generic_convex_kernel() -> None:
    hull = _static("hull", _cube(0.5))
    sphere = _dynamic(
        "sphere",
        SphereShape(0.5),
        Vec3(0.75, 0.08, 0.03),
    )

    manifold = detect_collision(hull, sphere)

    assert manifold is not None
    assert manifold.penetration > 0.0
    assert len(manifold.points) == 1
    assert manifold.points[0].feature_id.startswith("convex:")
    assert manifold.normal.x > 0.8


def test_convex_hull_hull_separation_and_overlap() -> None:
    first = _static("a", _cube(0.5))
    separated = _dynamic("b", _cube(0.5), Vec3(2.0, 0.0, 0.0))
    assert detect_collision(first, separated) is None

    separated.position = Vec3(0.8, 0.1, -0.05)
    separated.orientation = Quat.from_axis_angle(Vec3.axis(1), 0.12)
    overlap = detect_collision(first, separated)
    assert overlap is not None
    assert overlap.penetration > 0.0


def test_plane_convex_hull_support_contact_has_expected_penetration() -> None:
    floor = _static("floor", PlaneShape())
    hull = _dynamic(
        "hull",
        _cube(0.5),
        Vec3(0.0, 0.4, 0.0),
    )

    manifold = detect_collision(floor, hull)

    assert manifold is not None
    assert manifold.penetration == pytest.approx(0.1, abs=1.0e-8)
    assert manifold.normal == Vec3.axis(1)
    assert manifold.points[0].feature_id == "plane-convex_hull:support"


def test_convex_hull_raycast_hits_exact_face_and_inside_origin() -> None:
    body = _static("hull", _cube(0.5))
    outside = raycast_body(
        Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0),
        body,
    )
    inside = raycast_body(
        Ray(Vec3.zero(), Vec3(1.0, 2.0, 0.0), 10.0),
        body,
    )

    assert outside is not None
    assert outside.distance == pytest.approx(2.5, abs=1.0e-10)
    assert outside.point == Vec3(-0.5, 0.0, 0.0)
    assert outside.normal.x < -0.999999
    assert inside is not None
    assert inside.distance == 0.0
    assert inside.normal.dot(Vec3(1.0, 2.0, 0.0).normalized()) < -0.999999


def test_convex_hull_sphere_cast_hits_inflated_face() -> None:
    body = _static("hull", _cube(0.5))
    hit = sphere_cast_body(
        Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0),
        0.25,
        body,
    )

    assert hit is not None
    assert hit.distance == pytest.approx(2.25, abs=2.0e-5)
    assert hit.normal.x < -0.999


def test_continuous_convex_hull_participates_in_global_toi() -> None:
    moving = _dynamic(
        "moving",
        _cube(0.5),
        Vec3(-3.0, 0.0, 0.0),
        continuous=True,
    )
    moving.linear_velocity = Vec3(10.0, 0.0, 0.0)
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((moving, target), 0.5)

    assert event is not None
    assert event.time == pytest.approx(0.2, abs=3.0e-6)
    assert {event.body_a, event.body_b} == {"moving", "target"}


def test_world_solver_resolves_dynamic_hull_against_plane() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static("floor", PlaneShape()))
    hull = _dynamic(
        "hull",
        _cube(0.5),
        Vec3(0.0, 0.4, 0.0),
    )
    hull.linear_velocity = Vec3(0.0, -1.0, 0.0)
    world.add_body(hull)

    receipt = world.step()[0]

    assert receipt.manifolds == 1
    assert receipt.solver.normal_impulses > 0
    assert hull.linear_velocity.y > -1.0
