"""Typed rigid-body constraint solver regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    ConstraintSolver,
    DistanceJoint,
    DistanceLimitJoint,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PointJoint,
    RigidBody,
    SphereShape,
    SpringJoint,
    Vec3,
)


def _dynamic(body_id: str, x: float) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        SphereShape(0.5),
        position=Vec3(x, 0.0, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )


def _static(body_id: str, x: float = 0.0) -> RigidBody:
    return RigidBody.static(
        body_id,
        SphereShape(0.25),
        position=Vec3(x, 0.0, 0.0),
    )


def test_point_joint_pulls_two_anchors_toward_coincidence() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", 2.0)
    solver = ConstraintSolver(
        velocity_iterations=12,
        position_iterations=8,
        position_correction=0.8,
    )
    before = body.position.x

    stats = solver.solve(
        {"anchor": anchor, "body": body},
        (PointJoint("point", "anchor", "body", bias_factor=0.25),),
        dt=1.0 / 60.0,
    )

    assert body.position.x < before
    assert body.linear_velocity.x < 0.0
    assert stats.joints == 1
    assert stats.point_joints == 1
    assert stats.distance_joints == 0
    assert stats.spring_joints == 0
    assert stats.limit_joints == 0
    assert stats.velocity_impulses > 0
    assert stats.position_corrections > 0


def test_point_joint_supports_offset_local_anchors() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", 3.0)
    joint = PointJoint(
        "point",
        "anchor",
        "body",
        local_anchor_a=Vec3(1.0, 0.0, 0.0),
        local_anchor_b=Vec3(-1.0, 0.0, 0.0),
    )
    solver = ConstraintSolver(position_iterations=10)

    solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    world_anchor_a = anchor.position + anchor.orientation.rotate(joint.local_anchor_a)
    world_anchor_b = body.position + body.orientation.rotate(joint.local_anchor_b)
    assert (world_anchor_b - world_anchor_a).length() < 1.0


def test_spring_joint_accelerates_stretched_body_toward_rest_length() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", 3.0)
    joint = SpringJoint(
        "spring",
        "anchor",
        "body",
        rest_length=1.0,
        stiffness=120.0,
        damping=8.0,
    )
    solver = ConstraintSolver(velocity_iterations=12)

    stats = solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 120.0,
    )

    assert body.linear_velocity.x < 0.0
    assert stats.spring_joints == 1
    assert stats.velocity_impulses > 0
    assert stats.position_corrections == 0


def test_spring_joint_force_limit_bounds_accumulated_impulse() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", 10.0)
    joint = SpringJoint(
        "spring",
        "anchor",
        "body",
        rest_length=1.0,
        stiffness=10_000.0,
        damping=0.0,
        max_force=5.0,
    )
    solver = ConstraintSolver(velocity_iterations=32)
    dt = 0.1

    solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=dt,
    )

    momentum_change = body.mass * abs(body.linear_velocity.x)
    assert momentum_change <= pytest.approx(joint.max_force * dt, abs=1.0e-8)


def test_distance_limit_upper_bound_pulls_body_inward() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", 3.0)
    solver = ConstraintSolver(position_iterations=8)
    joint = DistanceLimitJoint(
        "limit",
        "anchor",
        "body",
        minimum_length=0.5,
        maximum_length=1.0,
        bias_factor=0.25,
    )

    before = body.position.x
    stats = solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position.x < before
    assert body.linear_velocity.x < 0.0
    assert stats.limit_joints == 1
    assert stats.maximum_error >= 2.0


def test_distance_limit_lower_bound_pushes_body_outward() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", 0.2)
    solver = ConstraintSolver(position_iterations=8)
    joint = DistanceLimitJoint(
        "limit",
        "anchor",
        "body",
        minimum_length=1.0,
        maximum_length=2.0,
        bias_factor=0.25,
    )

    before = body.position.x
    solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position.x > before
    assert body.linear_velocity.x > 0.0


def test_distance_limit_inside_band_is_inactive() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", 1.5)
    solver = ConstraintSolver()
    joint = DistanceLimitJoint(
        "limit",
        "anchor",
        "body",
        minimum_length=1.0,
        maximum_length=2.0,
    )

    position = body.position
    velocity = body.linear_velocity
    stats = solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position == position
    assert body.linear_velocity == velocity
    assert stats.velocity_impulses == 0
    assert stats.position_corrections == 0
    assert stats.maximum_error == 0.0


def test_mixed_joint_solver_orders_by_joint_id_but_counts_each_kind() -> None:
    anchor = _static("anchor")
    a = _dynamic("a", 2.0)
    b = _dynamic("b", 4.0)
    c = _dynamic("c", 6.0)
    joints = (
        SpringJoint("z-spring", "anchor", "a", rest_length=1.0),
        PointJoint("a-point", "a", "b"),
        DistanceLimitJoint(
            "m-limit",
            "b",
            "c",
            minimum_length=1.0,
            maximum_length=3.0,
        ),
        DistanceJoint("b-distance", "anchor", "c", rest_length=5.0),
    )

    stats = ConstraintSolver().solve(
        {"anchor": anchor, "a": a, "b": b, "c": c},
        joints,
        dt=1.0 / 60.0,
    )

    assert stats.joints == 4
    assert stats.distance_joints == 1
    assert stats.point_joints == 1
    assert stats.spring_joints == 1
    assert stats.limit_joints == 1


def test_joint_kind_and_parameters_are_bound_into_world_configuration_digest() -> None:
    left = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    right = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    for world in (left, right):
        world.add_body(_static("anchor"))
        world.add_body(_dynamic("body", 2.0))

    left.add_joint(
        SpringJoint(
            "joint",
            "anchor",
            "body",
            rest_length=1.0,
            stiffness=50.0,
            damping=5.0,
        )
    )
    right.add_joint(
        SpringJoint(
            "joint",
            "anchor",
            "body",
            rest_length=1.0,
            stiffness=75.0,
            damping=5.0,
        )
    )

    assert left.configuration_digest != right.configuration_digest
    assert left.state_digest != right.state_digest


def test_world_accepts_all_supported_joint_types() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    world.add_body(_static("anchor"))
    for index in range(4):
        world.add_body(_dynamic(f"body-{index}", float(index + 2)))

    world.add_joint(DistanceJoint("distance", "anchor", "body-0", rest_length=2.0))
    world.add_joint(PointJoint("point", "anchor", "body-1"))
    world.add_joint(SpringJoint("spring", "anchor", "body-2", rest_length=3.0))
    world.add_joint(
        DistanceLimitJoint(
            "limit",
            "anchor",
            "body-3",
            minimum_length=1.0,
            maximum_length=5.0,
        )
    )

    assert world.joint_ids() == ("distance", "limit", "point", "spring")
    receipt = world.step()[0]
    assert receipt.constraints.joints == 4
    assert receipt.constraints.distance_joints == 1
    assert receipt.constraints.point_joints == 1
    assert receipt.constraints.spring_joints == 1
    assert receipt.constraints.limit_joints == 1


def test_distance_limit_rejects_inverted_bounds() -> None:
    with pytest.raises(PhysicsValidationError, match="maximum_length"):
        DistanceLimitJoint(
            "bad",
            "a",
            "b",
            minimum_length=2.0,
            maximum_length=1.0,
        )


def test_spring_rejects_nonpositive_stiffness_and_force_limit() -> None:
    with pytest.raises(PhysicsValidationError, match="stiffness"):
        SpringJoint("bad", "a", "b", stiffness=0.0)
    with pytest.raises(PhysicsValidationError, match="max_force"):
        SpringJoint("bad-force", "a", "b", max_force=0.0)
