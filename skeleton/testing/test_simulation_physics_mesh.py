"""Triangle-mesh BVH, raycast, identity, and sphere-contact regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    AABB,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    Quat,
    Ray,
    RigidBody,
    SphereShape,
    TriangleMeshShape,
    Vec3,
    detect_collision,
)


def _floor_mesh(size: float = 2.0) -> TriangleMeshShape:
    s = size
    return TriangleMeshShape(
        (
            Vec3(-s, 0.0, -s),
            Vec3(s, 0.0, -s),
            Vec3(s, 0.0, s),
            Vec3(-s, 0.0, s),
        ),
        (
            (0, 2, 1),
            (0, 3, 2),
        ),
    )


def _static_mesh(
    *,
    position: Vec3 = Vec3(),
    orientation: Quat = Quat.identity(),
) -> RigidBody:
    return RigidBody.static(
        "mesh",
        _floor_mesh(),
        position=position,
        orientation=orientation,
    )


def test_mesh_builds_stable_bvh_and_geometry_fingerprint() -> None:
    left = _floor_mesh()
    right = _floor_mesh()

    assert left.geometry_fingerprint == right.geometry_fingerprint
    assert left.bvh_node_count == right.bvh_node_count
    assert left.bvh_node_count >= 1
    assert left.local_bounds.minimum == Vec3(-2.0, 0.0, -2.0)
    assert left.local_bounds.maximum == Vec3(2.0, 0.0, 2.0)


def test_mesh_geometry_fingerprint_changes_with_vertex_geometry() -> None:
    left = _floor_mesh(2.0)
    right = _floor_mesh(2.1)

    assert left.geometry_fingerprint != right.geometry_fingerprint


def test_mesh_rejects_degenerate_duplicate_and_out_of_range_triangles() -> None:
    vertices = (
        Vec3.zero(),
        Vec3.axis(0),
        Vec3.axis(2),
        Vec3(1.0, 0.0, 1.0),
    )
    degenerate_vertices = (
        Vec3.zero(),
        Vec3.axis(0),
        Vec3(2.0, 0.0, 0.0),
    )
    with pytest.raises(PhysicsValidationError, match="degenerate"):
        TriangleMeshShape(degenerate_vertices, ((0, 1, 2),))
    with pytest.raises(PhysicsValidationError, match="distinct"):
        TriangleMeshShape(vertices, ((0, 1, 1),))
    with pytest.raises(PhysicsValidationError, match="duplicate"):
        TriangleMeshShape(vertices, ((0, 1, 2), (2, 1, 0)))
    with pytest.raises(PhysicsValidationError, match="out of range"):
        TriangleMeshShape(vertices, ((0, 1, 8),))


def test_mesh_dynamic_mass_path_fails_closed() -> None:
    with pytest.raises(PhysicsValidationError, match="static geometry"):
        RigidBody.dynamic("mesh", _floor_mesh())


def test_mesh_candidate_query_is_sorted_and_culled() -> None:
    mesh = _floor_mesh()
    near_first = mesh.candidate_triangles(
        AABB(
            Vec3(-1.8, -0.1, -1.8),
            Vec3(-1.2, 0.1, -1.2),
        )
    )
    all_rows = mesh.candidate_triangles(
        AABB(
            Vec3(-3.0, -1.0, -3.0),
            Vec3(3.0, 1.0, 3.0),
        )
    )

    assert near_first == tuple(sorted(near_first))
    assert set(near_first).issubset({0, 1})
    assert all_rows == (0, 1)


def test_mesh_raycast_hits_floor_and_uses_stable_triangle_tie_break() -> None:
    mesh = _floor_mesh()
    hit = mesh.raycast_local(
        Vec3(0.0, 2.0, 0.0),
        -Vec3.axis(1),
        10.0,
    )

    assert hit is not None
    assert hit.distance == pytest.approx(2.0)
    assert hit.point == Vec3.zero()
    assert hit.normal == Vec3.axis(1)
    assert hit.triangle_index == 0
    assert sum(hit.barycentric) == pytest.approx(1.0)


def test_world_mesh_raycast_honors_rigid_transform() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    world.add_body(
        _static_mesh(
            position=Vec3(0.0, 3.0, 0.0),
            orientation=Quat.from_axis_angle(Vec3.axis(0), 0.0),
        )
    )

    hit = world.raycast_closest(
        Ray(Vec3(0.0, 5.0, 0.0), -Vec3.axis(1), 10.0)
    )

    assert hit is not None
    assert hit.body_id == "mesh"
    assert hit.distance == pytest.approx(2.0)
    assert hit.point.y == pytest.approx(3.0)
    assert hit.normal == Vec3.axis(1)


def test_world_mesh_identity_uses_geometry_fingerprint() -> None:
    left = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    right = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    left.add_body(RigidBody.static("mesh", _floor_mesh(2.0)))
    right.add_body(RigidBody.static("mesh", _floor_mesh(2.1)))

    assert left.configuration_digest != right.configuration_digest
    assert left.state_digest != right.state_digest


def test_sphere_above_mesh_gets_upward_contact() -> None:
    mesh = _static_mesh()
    sphere = RigidBody.dynamic(
        "sphere",
        SphereShape(0.5),
        position=Vec3(0.25, 0.4, 0.1),
        linear_damping=0.0,
        angular_damping=0.0,
    )

    manifold = detect_collision(mesh, sphere)

    assert manifold is not None
    assert manifold.normal.y > 0.999999
    assert manifold.penetration == pytest.approx(0.1, abs=1.0e-8)
    assert manifold.points[0].feature_id.startswith("mesh-sphere:t")


def test_sphere_below_mesh_gets_downward_two_sided_contact() -> None:
    mesh = _static_mesh()
    sphere = RigidBody.dynamic(
        "sphere",
        SphereShape(0.5),
        position=Vec3(-0.2, -0.4, 0.2),
        linear_damping=0.0,
        angular_damping=0.0,
    )

    manifold = detect_collision(mesh, sphere)

    assert manifold is not None
    assert manifold.normal.y < -0.999999
    assert manifold.penetration == pytest.approx(0.1, abs=1.0e-8)


def test_sphere_mesh_pair_reversal_flips_normal() -> None:
    mesh = _static_mesh()
    sphere = RigidBody.dynamic(
        "sphere",
        SphereShape(0.5),
        position=Vec3(0.1, 0.4, 0.1),
    )

    forward = detect_collision(mesh, sphere)
    reverse = detect_collision(sphere, mesh)

    assert forward is not None
    assert reverse is not None
    assert reverse.normal == -forward.normal
    assert reverse.points == forward.points


def test_world_solver_resolves_sphere_against_static_mesh() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static_mesh())
    sphere = RigidBody.dynamic(
        "sphere",
        SphereShape(0.5),
        position=Vec3(0.0, 0.4, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    sphere.linear_velocity = Vec3(0.0, -2.0, 0.0)
    world.add_body(sphere)

    receipt = world.step()[0]

    assert receipt.manifolds == 1
    assert receipt.solver.normal_impulses > 0
    assert sphere.linear_velocity.y > -2.0


def test_mesh_broad_phase_bounds_include_dynamic_sphere() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static_mesh())
    world.add_body(
        RigidBody.dynamic(
            "sphere",
            SphereShape(0.5),
            position=Vec3(0.0, 0.4, 0.0),
        )
    )

    receipt = world.step()[0]

    assert receipt.broad_phase_pairs == 1
    assert receipt.manifolds == 1
