"""Hinge alignment, limit, motor, and registry regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    ConstraintSolver,
    HingeJoint,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    Quat,
    RigidBody,
    SphereShape,
    Vec3,
)


def _dynamic(
    body_id: str,
    *,
    position: Vec3 = Vec3(),
    orientation: Quat = Quat.identity(),
) -> RigidBody:
    return RigidBody.dynamic(
        body_id,
        SphereShape(0.5),
        position=position,
        orientation=orientation,
        linear_damping=0.0,
        angular_damping=0.0,
    )


def _static(body_id: str) -> RigidBody:
    return RigidBody.static(body_id, SphereShape(0.25))


def _world_axis(body: RigidBody, local: Vec3) -> Vec3:
    return body.orientation.rotate(local).normalized()


def test_hinge_anchor_rows_pull_separated_centers_together() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(1.0, 0.5, 0.0))
    joint = HingeJoint(
        "hinge",
        "anchor",
        "body",
        bias_factor=0.2,
    )
    solver = ConstraintSolver(
        velocity_iterations=8,
        position_iterations=8,
        position_correction=0.8,
    )
    before = body.position.length()

    stats = solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position.length() < before
    assert stats.hinge_joints == 1
    assert stats.velocity_impulses > 0
    assert stats.position_corrections > 0


def test_hinge_axis_alignment_generates_corrective_angular_motion() -> None:
    anchor = _static("anchor")
    body = _dynamic(
        "body",
        orientation=Quat.from_axis_angle(Vec3.axis(2), math.radians(30.0)),
    )
    joint = HingeJoint(
        "hinge",
        "anchor",
        "body",
        local_axis_a=Vec3.axis(1),
        local_axis_b=Vec3.axis(1),
        local_reference_a=Vec3.axis(0),
        local_reference_b=Vec3.axis(0),
        bias_factor=0.1,
    )
    solver = ConstraintSolver(
        velocity_iterations=8,
        position_iterations=1,
    )

    axis_a_before = _world_axis(anchor, joint.local_axis_a)
    axis_b_before = _world_axis(body, joint.local_axis_b)
    before_alignment = axis_a_before.dot(axis_b_before)

    solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )
    assert abs(body.angular_velocity.z) > 0.0

    body.integrate_orientation(1.0 / 60.0)
    axis_a_after = _world_axis(anchor, joint.local_axis_a)
    axis_b_after = _world_axis(body, joint.local_axis_b)
    assert axis_a_after.dot(axis_b_after) > before_alignment


def test_hinge_motor_drives_target_twist_direction() -> None:
    anchor = _static("anchor")
    body = _dynamic("body")
    joint = HingeJoint(
        "hinge",
        "anchor",
        "body",
        motor_speed=4.0,
        max_motor_torque=10.0,
    )

    stats = ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=0.1,
    )

    assert body.angular_velocity.y > 0.0
    assert stats.hinge_joints == 1
    assert stats.velocity_impulses > 0


def test_hinge_motor_respects_torque_impulse_budget() -> None:
    anchor = _static("anchor")
    body = _dynamic("body")
    joint = HingeJoint(
        "hinge",
        "anchor",
        "body",
        motor_speed=1000.0,
        max_motor_torque=2.0,
    )
    dt = 0.1

    ConstraintSolver(velocity_iterations=32).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=dt,
    )

    world_inertia = (
        body.orientation.to_matrix()
        .mul_mat(body.local_inertia)
        .mul_mat(body.orientation.to_matrix().transpose())
    )
    angular_momentum = world_inertia.mul_vec(body.angular_velocity)
    assert abs(angular_momentum.y) <= joint.max_motor_torque * dt + 1.0e-8


def test_hinge_upper_limit_pushes_twist_back_toward_allowed_interval() -> None:
    anchor = _static("anchor")
    body = _dynamic(
        "body",
        orientation=Quat.from_axis_angle(Vec3.axis(1), 0.8),
    )
    joint = HingeJoint(
        "hinge",
        "anchor",
        "body",
        lower_angle=-0.25,
        upper_angle=0.25,
        bias_factor=0.2,
    )

    stats = ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.angular_velocity.y < 0.0
    assert stats.maximum_error >= 0.5


def test_hinge_lower_limit_pushes_twist_up_toward_allowed_interval() -> None:
    anchor = _static("anchor")
    body = _dynamic(
        "body",
        orientation=Quat.from_axis_angle(Vec3.axis(1), -0.8),
    )
    joint = HingeJoint(
        "hinge",
        "anchor",
        "body",
        lower_angle=-0.25,
        upper_angle=0.25,
        bias_factor=0.2,
    )

    ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.angular_velocity.y > 0.0


def test_hinge_inside_limits_does_not_create_twist_impulse_without_motor() -> None:
    anchor = _static("anchor")
    body = _dynamic(
        "body",
        orientation=Quat.from_axis_angle(Vec3.axis(1), 0.1),
    )
    joint = HingeJoint(
        "hinge",
        "anchor",
        "body",
        lower_angle=-0.25,
        upper_angle=0.25,
    )

    ConstraintSolver(velocity_iterations=8).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.angular_velocity.y == pytest.approx(0.0, abs=1.0e-12)


def test_hinge_free_axis_does_not_resist_existing_twist_without_motor_or_limit() -> None:
    anchor = _static("anchor")
    body = _dynamic("body")
    body.angular_velocity = Vec3(0.0, 3.0, 0.0)
    joint = HingeJoint("hinge", "anchor", "body")

    ConstraintSolver(velocity_iterations=8).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.angular_velocity.y == pytest.approx(3.0, abs=1.0e-9)


def test_hinge_parameters_are_bound_into_world_configuration_identity() -> None:
    left = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    right = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    for world in (left, right):
        world.add_body(_static("anchor"))
        world.add_body(_dynamic("body"))

    left.add_joint(
        HingeJoint(
            "hinge",
            "anchor",
            "body",
            motor_speed=2.0,
            max_motor_torque=5.0,
        )
    )
    right.add_joint(
        HingeJoint(
            "hinge",
            "anchor",
            "body",
            motor_speed=3.0,
            max_motor_torque=5.0,
        )
    )

    assert left.configuration_digest != right.configuration_digest
    assert left.state_digest != right.state_digest


def test_world_receipt_counts_hinge_joint_through_island_solver() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static("anchor"))
    world.add_body(_dynamic("body", position=Vec3(2.0, 0.0, 0.0)))
    world.add_joint(
        HingeJoint(
            "hinge",
            "anchor",
            "body",
            local_anchor_a=Vec3(2.0, 0.0, 0.0),
            motor_speed=1.0,
            max_motor_torque=1.0,
        )
    )

    receipt = world.step()[0]
    assert receipt.constraints.joints == 1
    assert receipt.constraints.hinge_joints == 1
    assert receipt.islands.joints == 1


def test_hinge_rejects_zero_axis() -> None:
    with pytest.raises(PhysicsValidationError, match="local_axis_a"):
        HingeJoint(
            "bad",
            "a",
            "b",
            local_axis_a=Vec3.zero(),
        )


def test_hinge_rejects_reference_parallel_to_axis() -> None:
    with pytest.raises(PhysicsValidationError, match="local_reference_a"):
        HingeJoint(
            "bad",
            "a",
            "b",
            local_axis_a=Vec3.axis(1),
            local_reference_a=Vec3.axis(1),
        )


def test_hinge_rejects_unpaired_motor_configuration() -> None:
    with pytest.raises(PhysicsValidationError, match="requires"):
        HingeJoint(
            "bad",
            "a",
            "b",
            motor_speed=1.0,
        )
    with pytest.raises(PhysicsValidationError, match="requires"):
        HingeJoint(
            "bad-torque",
            "a",
            "b",
            max_motor_torque=1.0,
        )


def test_hinge_rejects_inverted_or_unwrapped_limits() -> None:
    with pytest.raises(PhysicsValidationError, match="upper_angle"):
        HingeJoint(
            "bad",
            "a",
            "b",
            lower_angle=0.5,
            upper_angle=-0.5,
        )
    with pytest.raises(PhysicsValidationError, match="lower_angle"):
        HingeJoint(
            "bad-range",
            "a",
            "b",
            lower_angle=-math.pi - 0.01,
        )
