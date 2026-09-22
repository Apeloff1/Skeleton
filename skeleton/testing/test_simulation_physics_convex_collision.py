"""Capsule/cylinder narrow-phase and solver integration regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CapsuleShape,
    CylinderShape,
    PhysicsSettings,
    PhysicsWorld,
    PlaneShape,
    Quat,
    RigidBody,
    SphereShape,
    Vec3,
    detect_collision,
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
) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        shape,
        position=position,
        orientation=orientation,
        linear_damping=0.0,
        angular_damping=0.0,
    )


@pytest.mark.parametrize(
    ("shape_a", "shape_b", "offset"),
    (
        (CapsuleShape(0.5, 0.8), SphereShape(0.5), 0.8),
        (CapsuleShape(0.5, 0.8), BoxShape(Vec3(0.4, 0.4, 0.4)), 0.7),
        (CylinderShape(0.5, 0.8), SphereShape(0.5), 0.8),
        (CylinderShape(0.5, 0.8), BoxShape(Vec3(0.4, 0.4, 0.4)), 0.7),
        (CapsuleShape(0.5, 0.8), CapsuleShape(0.5, 0.8), 0.8),
        (CylinderShape(0.5, 0.8), CylinderShape(0.5, 0.8), 0.8),
        (CapsuleShape(0.5, 0.8), CylinderShape(0.5, 0.8), 0.8),
    ),
)
def test_round_convex_pairings_generate_positive_contact(
    shape_a,
    shape_b,
    offset: float,
) -> None:
    a = _static(
        "a",
        shape_a,
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.radians(4.0)),
    )
    b = _dynamic(
        "b",
        shape_b,
        position=Vec3(offset, 0.03, -0.02),
        orientation=Quat.from_axis_angle(Vec3.axis(0), math.radians(-3.0)),
    )

    manifold = detect_collision(a, b)

    assert manifold is not None
    assert manifold.penetration > 0.0
    assert len(manifold.points) == 1
    assert manifold.points[0].feature_id.startswith("convex:")
    assert manifold.normal.length() == pytest.approx(1.0)
    assert (b.position - a.position).dot(manifold.normal) >= -1.0e-8


@pytest.mark.parametrize(
    ("shape_a", "shape_b"),
    (
        (CapsuleShape(0.5, 0.8), SphereShape(0.5)),
        (CylinderShape(0.5, 0.8), BoxShape(Vec3(0.4, 0.4, 0.4))),
        (CapsuleShape(0.5, 0.8), CylinderShape(0.5, 0.8)),
    ),
)
def test_round_convex_pairings_reject_clear_separation(shape_a, shape_b) -> None:
    a = _static("a", shape_a)
    b = _dynamic("b", shape_b, position=Vec3(5.0, 0.0, 0.0))

    assert detect_collision(a, b) is None


def test_plane_capsule_uses_exact_deepest_support_penetration() -> None:
    plane = _static("ground", PlaneShape())
    capsule = _dynamic(
        "capsule",
        CapsuleShape(0.5, 0.8),
        position=Vec3(0.0, 1.2, 0.0),
    )

    manifold = detect_collision(plane, capsule)

    assert manifold is not None
    assert manifold.normal == Vec3.axis(1)
    assert manifold.penetration == pytest.approx(0.1)
    assert manifold.points[0].feature_id == "plane-capsule:support"
    assert manifold.points[0].position.y == pytest.approx(-0.05)


def test_plane_cylinder_uses_cap_support_penetration() -> None:
    plane = _static("ground", PlaneShape())
    cylinder = _dynamic(
        "cylinder",
        CylinderShape(0.5, 1.0),
        position=Vec3(0.0, 0.9, 0.0),
    )

    manifold = detect_collision(plane, cylinder)

    assert manifold is not None
    assert manifold.normal == Vec3.axis(1)
    assert manifold.penetration == pytest.approx(0.1)
    assert manifold.points[0].feature_id == "plane-cylinder:support"


def test_round_shape_plane_pair_reversal_flips_normal_and_preserves_point() -> None:
    plane = _static("ground", PlaneShape())
    capsule = _dynamic(
        "capsule",
        CapsuleShape(0.5, 0.8),
        position=Vec3(0.0, 1.2, 0.0),
    )

    forward = detect_collision(plane, capsule)
    reverse = detect_collision(capsule, plane)

    assert forward is not None
    assert reverse is not None
    assert reverse.body_a == "capsule"
    assert reverse.body_b == "ground"
    assert reverse.normal == -forward.normal
    assert reverse.points == forward.points


def test_convex_pair_reversal_preserves_penetration_and_opposes_normal() -> None:
    capsule = _static("capsule", CapsuleShape(0.5, 0.8))
    cylinder = _dynamic(
        "cylinder",
        CylinderShape(0.5, 0.8),
        position=Vec3(0.75, 0.05, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), 0.1),
    )

    forward = detect_collision(capsule, cylinder)
    reverse = detect_collision(cylinder, capsule)

    assert forward is not None
    assert reverse is not None
    assert reverse.penetration == pytest.approx(forward.penetration, rel=2.0e-4)
    assert reverse.normal.dot(forward.normal) < -0.99


def test_convex_feature_identity_survives_small_topology_preserving_motion() -> None:
    capsule = _static("capsule", CapsuleShape(0.5, 0.8))
    cylinder = _dynamic(
        "cylinder",
        CylinderShape(0.5, 0.8),
        position=Vec3(0.75, 0.03, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), 0.08),
    )

    first = detect_collision(capsule, cylinder)
    assert first is not None

    cylinder.position = cylinder.position + Vec3(1.0e-4, -5.0e-5, 8.0e-5)
    second = detect_collision(capsule, cylinder)

    assert second is not None
    assert second.points[0].feature_id == first.points[0].feature_id


def test_world_solver_stops_capsule_moving_into_plane() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 120.0,
            velocity_iterations=12,
            position_iterations=6,
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static("ground", PlaneShape()))
    capsule = _dynamic(
        "capsule",
        CapsuleShape(0.5, 0.8),
        position=Vec3(0.0, 1.2, 0.0),
    )
    capsule.linear_velocity = Vec3(0.0, -2.0, 0.0)
    world.add_body(capsule)

    before_y = capsule.position.y
    receipt = world.step()[0]

    assert receipt.manifolds == 1
    assert receipt.contact_points == 1
    assert receipt.solver.normal_impulses > 0
    assert capsule.linear_velocity.y > -2.0
    assert capsule.position.y > before_y - 2.0 * world.settings.fixed_dt


def test_world_solver_generates_convex_contact_impulse_and_cache() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=1.0 / 240.0,
            velocity_iterations=12,
            position_iterations=4,
            sleep_after_seconds=10.0,
        )
    )
    capsule = _static("capsule", CapsuleShape(0.5, 0.8))
    cylinder = _dynamic(
        "cylinder",
        CylinderShape(0.5, 0.8),
        position=Vec3(0.8, 0.04, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), 0.05),
    )
    cylinder.linear_velocity = Vec3(-2.0, 0.0, 0.0)
    world.add_body(capsule)
    world.add_body(cylinder)

    first = world.step()[0]

    assert first.manifolds == 1
    assert first.solver.normal_impulses > 0
    assert first.solver.cached_contacts == 1
    assert world.contact_cache_size() == 1
    assert cylinder.linear_velocity.x > -2.0

    second = world.step()[0]
    assert second.solver.cached_contacts >= 1


def test_broad_phase_includes_capsule_and_cylinder_aabbs() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    world.add_body(
        _static(
            "capsule",
            CapsuleShape(0.5, 0.8),
            position=Vec3(0.0, 0.0, 0.0),
        )
    )
    world.add_body(
        _dynamic(
            "cylinder",
            CylinderShape(0.5, 0.8),
            position=Vec3(0.8, 0.0, 0.0),
        )
    )

    receipt = world.step()[0]

    assert receipt.broad_phase_pairs == 1
    assert receipt.manifolds == 1
