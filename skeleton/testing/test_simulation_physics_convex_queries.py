"""Capsule/cylinder scene-query and continuous-sphere CCD regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    CapsuleShape,
    ContinuousCollisionDetector,
    CylinderShape,
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


def _static(body_id: str, shape, *, position: Vec3 = Vec3(), orientation: Quat = Quat.identity()):
    return RigidBody.static(
        body_id,
        shape,
        position=position,
        orientation=orientation,
    )


def test_capsule_raycast_hits_cylindrical_side() -> None:
    body = _static("capsule", CapsuleShape(0.5, 1.0))
    ray = Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0)

    hit = raycast_body(ray, body)

    assert hit is not None
    assert hit.distance == pytest.approx(2.5)
    assert hit.point == Vec3(-0.5, 0.0, 0.0)
    assert hit.normal == -Vec3.axis(0)


def test_capsule_raycast_hits_spherical_cap() -> None:
    body = _static("capsule", CapsuleShape(0.5, 1.0))
    ray = Ray(Vec3(0.0, 3.0, 0.0), -Vec3.axis(1), 10.0)

    hit = raycast_body(ray, body)

    assert hit is not None
    assert hit.distance == pytest.approx(1.5)
    assert hit.point == Vec3(0.0, 1.5, 0.0)
    assert hit.normal == Vec3.axis(1)


def test_cylinder_raycast_hits_side_and_cap_exactly() -> None:
    body = _static("cylinder", CylinderShape(0.5, 1.0))

    side = raycast_body(
        Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0),
        body,
    )
    cap = raycast_body(
        Ray(Vec3(0.0, 3.0, 0.0), -Vec3.axis(1), 10.0),
        body,
    )

    assert side is not None
    assert side.distance == pytest.approx(2.5)
    assert side.normal == -Vec3.axis(0)
    assert cap is not None
    assert cap.distance == pytest.approx(2.0)
    assert cap.normal == Vec3.axis(1)


def test_rotated_capsule_raycast_uses_body_transform() -> None:
    body = _static(
        "capsule",
        CapsuleShape(0.5, 1.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.pi * 0.5),
    )
    ray = Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0)

    hit = raycast_body(ray, body)

    assert hit is not None
    assert hit.distance == pytest.approx(1.5)
    assert hit.point.x == pytest.approx(-1.5)
    assert hit.normal.x < -0.999999


@pytest.mark.parametrize(
    "shape",
    (
        CapsuleShape(0.5, 1.0),
        CylinderShape(0.5, 1.0),
    ),
)
def test_round_shape_raycast_inside_origin_returns_zero_distance(shape) -> None:
    body = _static("shape", shape)
    ray = Ray(Vec3.zero(), Vec3(1.0, 2.0, 0.0), 10.0)

    hit = raycast_body(ray, body)

    assert hit is not None
    assert hit.distance == 0.0
    assert hit.point == Vec3.zero()
    assert hit.normal.dot(ray.direction) < -0.999999


def test_sphere_cast_capsule_is_exact_radius_expansion() -> None:
    body = _static("capsule", CapsuleShape(0.5, 1.0))
    ray = Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0)

    hit = sphere_cast_body(ray, 0.25, body)

    assert hit is not None
    assert hit.distance == pytest.approx(2.25)
    assert hit.point == Vec3(-0.75, 0.0, 0.0)
    assert hit.normal == -Vec3.axis(0)


def test_sphere_cast_cylinder_side_is_exact() -> None:
    body = _static("cylinder", CylinderShape(0.5, 1.0))
    ray = Ray(Vec3(-3.0, 0.0, 0.0), Vec3.axis(0), 10.0)

    hit = sphere_cast_body(ray, 0.25, body)

    assert hit is not None
    assert hit.distance == pytest.approx(2.25, abs=1.0e-7)
    assert hit.normal.x < -0.999999


def test_sphere_cast_cylinder_uses_rounded_rim_not_expanded_box_corner() -> None:
    body = _static("cylinder", CylinderShape(0.5, 1.0))
    ray = Ray(Vec3(-3.0, 1.2, 0.0), Vec3.axis(0), 10.0)
    sphere_radius = 0.25

    hit = sphere_cast_body(ray, sphere_radius, body)

    expected_x = -(0.5 + math.sqrt(sphere_radius**2 - 0.2**2))
    expected_distance = 3.0 + expected_x
    assert hit is not None
    assert hit.distance == pytest.approx(expected_distance, abs=2.0e-6)
    assert hit.distance > 2.25
    assert hit.normal.x < 0.0
    assert hit.normal.y > 0.0


def test_sphere_cast_cylinder_clear_corner_miss_returns_none() -> None:
    body = _static("cylinder", CylinderShape(0.5, 1.0))
    ray = Ray(Vec3(-3.0, 1.3, 0.0), Vec3.axis(0), 10.0)

    assert sphere_cast_body(ray, 0.25, body) is None


def test_world_raycast_orders_capsule_and_cylinder_hits() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    world.add_body(
        _static(
            "capsule",
            CapsuleShape(0.5, 1.0),
            position=Vec3(-1.0, 0.0, 0.0),
        )
    )
    world.add_body(
        _static(
            "cylinder",
            CylinderShape(0.5, 1.0),
            position=Vec3(2.0, 0.0, 0.0),
        )
    )

    hits = world.raycast(
        Ray(Vec3(-5.0, 0.0, 0.0), Vec3.axis(0), 20.0)
    )

    assert tuple(hit.body_id for hit in hits) == ("capsule", "cylinder")
    assert hits[0].distance < hits[1].distance


def _continuous_sphere(body_id: str, velocity: Vec3) -> RigidBody:
    body = RigidBody.dynamic(
        body_id,
        SphereShape(0.2),
        position=Vec3(-3.0, 0.0, 0.0),
        continuous=True,
        linear_damping=0.0,
        angular_damping=0.0,
    )
    body.linear_velocity = velocity
    return body


@pytest.mark.parametrize(
    "target_shape",
    (
        CapsuleShape(0.5, 1.0),
        CylinderShape(0.5, 1.0),
    ),
)
def test_continuous_sphere_ccd_hits_static_round_target(target_shape) -> None:
    moving = _continuous_sphere("moving", Vec3(10.0, 0.0, 0.0))
    target = _static("target", target_shape)
    detector = ContinuousCollisionDetector(motion_threshold=0.1)
    dt = 0.5

    hit = detector.sweep(moving, (moving, target), dt)

    assert hit is not None
    assert hit.target_body == "target"
    assert hit.distance == pytest.approx(2.3, abs=2.0e-6)
    assert hit.fraction == pytest.approx(2.3 / 5.0, abs=1.0e-6)
    assert hit.normal.x < -0.999999


def test_ccd_earliest_event_includes_capsule_target_in_global_order() -> None:
    moving = _continuous_sphere("moving", Vec3(12.0, 0.0, 0.0))
    near = _static(
        "near",
        CapsuleShape(0.5, 1.0),
        position=Vec3(0.0, 0.0, 0.0),
    )
    far = _static(
        "far",
        CylinderShape(0.5, 1.0),
        position=Vec3(2.0, 0.0, 0.0),
    )
    detector = ContinuousCollisionDetector(motion_threshold=0.1)

    event = detector.earliest_event((moving, far, near), 0.5)

    assert event is not None
    assert {event.body_a, event.body_b} == {"moving", "near"}
    assert event.time < 0.5


def test_world_ccd_prevents_fast_sphere_from_skipping_static_cylinder() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.25,
            ccd_motion_threshold=0.1,
            max_ccd_substeps=8,
            sleep_after_seconds=10.0,
        )
    )
    moving = _continuous_sphere("moving", Vec3(20.0, 0.0, 0.0))
    target = _static("target", CylinderShape(0.5, 1.0))
    world.add_body(moving)
    world.add_body(target)

    receipt = world.step()[0]

    assert receipt.ccd_hits >= 1
    assert moving.position.x < 1.0
