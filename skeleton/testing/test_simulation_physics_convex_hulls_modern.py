"""Modern convex-hull topology, mass, collision, CCD, and gameplay regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    ContinuousCollisionDetector,
    ConvexHullShape,
    KinematicCapsuleController,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    RigidBody,
    SphereShape,
    Vec3,
    convex_distance,
    convex_plane_time_of_impact,
    convex_time_of_impact,
    detect_collision,
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
        linear_damping=0.0,
        angular_damping=0.0,
        continuous=continuous,
    )


def test_cube_hull_support_uses_stable_lowest_vertex_tie_break() -> None:
    hull = _cube_hull()
    body = _static("hull", hull, Vec3(2.0, 3.0, 4.0))

    support = hull.support(Vec3.axis(0), body.transform)

    # Four vertices share max local x. Index 1 is the stable lowest-index winner.
    assert support == Vec3(3.0, 2.0, 3.0)


def test_cube_hull_support_and_aabb_transform_exactly() -> None:
    hull = _cube_hull()
    body = _static(
        "hull",
        hull,
        Vec3(2.0, 3.0, 4.0),
        Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5),
    )

    bounds = hull.aabb(body.transform)
    assert bounds.minimum.almost_equal(
        Vec3(1.0, 2.0, 3.0),
        tolerance=1.0e-12,
    )
    assert bounds.maximum.almost_equal(
        Vec3(3.0, 4.0, 5.0),
        tolerance=1.0e-12,
    )

    for direction in (
        Vec3.axis(0),
        -Vec3.axis(0),
        Vec3.axis(1),
        -Vec3.axis(1),
        Vec3.axis(2),
        -Vec3.axis(2),
    ):
        assert bounds.contains(hull.support(direction, body.transform))


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
    assert hull_props.inertia.to_tuple() == pytest.approx(
        box_props.inertia.to_tuple(),
        rel=1.0e-9,
        abs=1.0e-10,
    )


@pytest.mark.parametrize("half", (1.0e-5, 1.0e5))
def test_hull_validation_and_mass_properties_are_scale_invariant(
    half: float,
) -> None:
    hull = _cube_hull(half)
    box = BoxShape(Vec3.one() * half)

    hull_props = hull.mass_properties(1.0)
    box_props = box.mass_properties(1.0)

    assert hull_props.mass == pytest.approx(box_props.mass, rel=2.0e-9)
    assert hull_props.center_of_mass.almost_equal(
        Vec3.zero(),
        tolerance=max(1.0e-14, half * 1.0e-10),
    )
    assert hull_props.inertia.m00 == pytest.approx(
        box_props.inertia.m00,
        rel=3.0e-9,
    )
    assert hull_props.inertia.m11 == pytest.approx(
        box_props.inertia.m11,
        rel=3.0e-9,
    )
    assert hull_props.inertia.m22 == pytest.approx(
        box_props.inertia.m22,
        rel=3.0e-9,
    )


def test_reversing_all_hull_faces_preserves_mass_properties() -> None:
    hull = _cube_hull()
    reversed_hull = ConvexHullShape(
        hull.vertices,
        tuple((face[0], face[2], face[1]) for face in hull.faces),
    )

    left = hull.mass_properties(1.0)
    right = reversed_hull.mass_properties(1.0)

    assert right.mass == pytest.approx(left.mass)
    assert right.center_of_mass.almost_equal(
        left.center_of_mass,
        tolerance=1.0e-12,
    )
    assert right.inertia.to_tuple() == pytest.approx(
        left.inertia.to_tuple(),
        rel=1.0e-10,
        abs=1.0e-12,
    )


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
    vertices[6] = Vec3.zero()

    with pytest.raises(PhysicsValidationError, match="convex"):
        ConvexHullShape(tuple(vertices), hull.faces)


def test_hull_rejects_duplicate_vertices() -> None:
    hull = _cube_hull()
    vertices = list(hull.vertices)
    vertices[-1] = vertices[0]

    with pytest.raises(PhysicsValidationError, match="unique"):
        ConvexHullShape(tuple(vertices), hull.faces)


def test_hull_rejects_degenerate_triangle() -> None:
    hull = _cube_hull()
    vertices = list(hull.vertices)
    # Move vertex 2 onto the edge from 0 to 1 so face (0, 2, 1)
    # contains three distinct but geometrically collinear vertices.
    vertices[2] = Vec3(0.0, -1.0, -1.0)

    with pytest.raises(PhysicsValidationError, match="degenerate"):
        ConvexHullShape(tuple(vertices), hull.faces)


def test_hull_vertex_bound_fails_before_expensive_topology_work() -> None:
    vertices = tuple(
        Vec3(float(index), float(index % 7), float(index % 11))
        for index in range(4097)
    )

    with pytest.raises(PhysicsValidationError, match="vertex bound"):
        ConvexHullShape(vertices, ((0, 1, 2),) * 4)


def test_hull_face_bound_fails_before_face_validation() -> None:
    hull = _cube_hull()
    faces = ((0, 1, 2),) * 8193

    with pytest.raises(PhysicsValidationError, match="face bound"):
        ConvexHullShape(hull.vertices, faces)


def test_centered_hull_can_create_dynamic_rigid_body() -> None:
    body = _dynamic("hull", _cube_hull())

    assert body.mass > 0.0
    assert body.local_inertia.is_invertible()
    assert body.local_inverse_inertia.is_invertible()


def test_offset_hull_fails_existing_dynamic_center_of_mass_contract() -> None:
    hull = _cube_hull()
    shifted = ConvexHullShape(
        tuple(
            vertex + Vec3(1.0, 0.0, 0.0)
            for vertex in hull.vertices
        ),
        hull.faces,
    )

    with pytest.raises(PhysicsValidationError, match="offset centers"):
        _dynamic("shifted", shifted)


def test_hull_topology_binds_world_configuration_and_state_identity() -> None:
    left = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    right = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    left.add_body(_dynamic("hull", _cube_hull(1.0)))
    right.add_body(_dynamic("hull", _cube_hull(1.1)))

    assert left.configuration_digest != right.configuration_digest
    assert left.state_digest != right.state_digest


def test_convex_distance_hull_sphere_matches_axis_gap() -> None:
    hull = _static("hull", _cube_hull(), Vec3.zero())
    sphere = _static(
        "sphere",
        SphereShape(0.5),
        Vec3(3.0, 0.0, 0.0),
    )

    result = convex_distance(hull, sphere)

    assert not result.intersects
    assert result.distance == pytest.approx(1.5, abs=1.0e-8)
    assert result.normal.x > 0.999999
    assert result.point_a.x == pytest.approx(1.0, abs=1.0e-8)
    assert result.point_b.x == pytest.approx(2.5, abs=1.0e-8)


def test_convex_distance_hull_pair_reversal_swaps_witnesses() -> None:
    hull = _static("hull", _cube_hull(), Vec3(-2.0, 0.0, 0.0))
    sphere = _static(
        "sphere",
        SphereShape(0.5),
        Vec3(2.0, 0.0, 0.0),
    )

    forward = convex_distance(hull, sphere)
    reverse = convex_distance(sphere, hull)

    assert reverse.distance == pytest.approx(forward.distance, rel=1.0e-8)
    assert reverse.normal.dot(forward.normal) < -0.999999
    assert reverse.point_a.almost_equal(
        forward.point_b,
        tolerance=1.0e-8,
    )
    assert reverse.point_b.almost_equal(
        forward.point_a,
        tolerance=1.0e-8,
    )


def test_convex_distance_returns_zero_for_hull_overlap() -> None:
    hull = _static("hull", _cube_hull())
    sphere = _static(
        "sphere",
        SphereShape(0.75),
        Vec3(0.5, 0.0, 0.0),
    )

    result = convex_distance(hull, sphere)

    assert result.intersects
    assert result.distance == pytest.approx(0.0)


def test_hull_hull_collision_uses_current_generic_convex_kernel() -> None:
    a = _static("a", _cube_hull())
    b = _dynamic("b", _cube_hull(), Vec3(1.5, 0.0, 0.0))

    manifold = detect_collision(a, b)

    assert manifold is not None
    assert manifold.penetration > 0.0
    assert manifold.points[0].feature_id.startswith(
        "convex:convex_hull:convex_hull"
    )
    assert manifold.normal.x > 0.9


def test_hull_box_collision_uses_generic_path_without_replacing_box_box() -> None:
    hull = _static("hull", _cube_hull())
    box = _dynamic(
        "box",
        BoxShape(Vec3.one()),
        Vec3(1.5, 0.0, 0.0),
    )

    manifold = detect_collision(hull, box)

    assert manifold is not None
    assert manifold.penetration > 0.0
    assert manifold.points[0].feature_id.startswith(
        "convex:convex_hull:box"
    )


def test_plane_hull_contact_uses_deepest_support() -> None:
    plane = _static("ground", PlaneShape())
    hull = _dynamic(
        "hull",
        _cube_hull(),
        Vec3(0.0, 0.8, 0.0),
    )

    manifold = detect_collision(plane, hull)

    assert manifold is not None
    assert manifold.penetration == pytest.approx(0.2, abs=1.0e-7)
    assert manifold.normal == Vec3.axis(1)
    assert manifold.points[0].feature_id == (
        "plane-convex_hull:support"
    )


def test_world_solver_resolves_dynamic_hull_against_plane() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static("ground", PlaneShape()))
    hull = _dynamic(
        "hull",
        _cube_hull(),
        Vec3(0.0, 0.8, 0.0),
    )
    hull.linear_velocity = Vec3(0.0, -1.0, 0.0)
    world.add_body(hull)

    receipt = world.step()[0]

    assert receipt.manifolds == 1
    assert receipt.solver.normal_impulses > 0
    assert hull.linear_velocity.y > -1.0


def test_convex_hull_linear_toi_matches_cube_face_contact() -> None:
    moving = _dynamic(
        "moving",
        _cube_hull(0.5),
        Vec3(-3.0, 0.0, 0.0),
        continuous=True,
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

    assert hit is not None
    assert hit.time == pytest.approx(0.2, abs=3.0e-6)
    assert hit.normal.x > 0.999


def test_global_ccd_admits_fast_continuous_hull() -> None:
    moving = _dynamic(
        "moving",
        _cube_hull(0.5),
        Vec3(-3.0, 0.0, 0.0),
        continuous=True,
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
    assert {event.body_a, event.body_b} == {"moving", "target"}
    assert event.time == pytest.approx(0.2, abs=3.0e-6)


def test_world_ccd_prevents_fast_hull_tunneling_through_box() -> None:
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
        _cube_hull(0.5),
        Vec3(-3.0, 0.0, 0.0),
        continuous=True,
    )
    moving.linear_velocity = Vec3(10.0, 0.0, 0.0)
    target = _static(
        "target",
        BoxShape(Vec3(0.5, 0.5, 0.5)),
    )
    world.add_body(moving)
    world.add_body(target)

    receipt = world.step()[0]

    assert receipt.ccd_clamps >= 1
    assert moving.position.x < target.position.x
    assert moving.linear_velocity.x < 10.0


def test_convex_hull_plane_toi_uses_hull_support_radius() -> None:
    moving = _dynamic(
        "hull",
        _cube_hull(0.5),
        Vec3(0.0, 3.0, 0.0),
        continuous=True,
    )
    plane = _static("plane", PlaneShape())
    moving.linear_velocity = Vec3(0.0, -10.0, 0.0)

    hit = convex_plane_time_of_impact(
        moving,
        plane,
        0.5,
        distance_tolerance=1.0e-8,
    )

    assert hit is not None
    assert hit.time == pytest.approx(0.25, abs=3.0e-6)


def test_character_capsule_sweep_stops_before_convex_hull_wall() -> None:
    controller = KinematicCapsuleController(
        "character",
        position=Vec3(0.0, 1.0, 0.0),
    )
    wall = _static(
        "hull-wall",
        _cube_hull(0.5),
        Vec3(2.0, 1.0, 0.0),
    )

    result = controller.move(
        Vec3(3.0, 0.0, 0.0),
        (wall,),
        dt=1.0,
    )

    assert result.hits
    assert result.hits[0].body_id == "hull-wall"
    assert result.position.x < 1.2
    assert result.hits[0].normal.x < -0.9


def test_hull_collision_is_deterministic_under_repeated_query() -> None:
    a = _static(
        "a",
        _cube_hull(),
        orientation=Quat.from_axis_angle(Vec3.axis(1), 0.2),
    )
    b = _dynamic(
        "b",
        _cube_hull(),
        Vec3(1.4, 0.1, -0.1),
        Quat.from_axis_angle(Vec3.axis(2), -0.17),
    )

    first = detect_collision(a, b)
    second = detect_collision(a, b)

    assert first == second
