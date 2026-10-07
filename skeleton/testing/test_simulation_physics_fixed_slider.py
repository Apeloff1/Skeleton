"""Fixed-frame and prismatic/slider joint regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    ConstraintSolver,
    FixedJoint,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    Quat,
    RigidBody,
    SliderJoint,
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


def _orientation_error(a: Quat, b: Quat) -> float:
    relative = (b * a.conjugate()).normalized()
    w = abs(relative.w)
    w = max(-1.0, min(1.0, w))
    return 2.0 * math.acos(w)


def test_fixed_joint_corrects_translation_and_rotation() -> None:
    anchor = _static("anchor")
    body = _dynamic(
        "body",
        position=Vec3(1.0, 0.5, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), 0.4),
    )
    joint = FixedJoint("fixed", "anchor", "body", bias_factor=0.2)
    solver = ConstraintSolver(
        velocity_iterations=12,
        position_iterations=8,
        position_correction=0.8,
    )

    before_position_error = body.position.length()
    before_orientation_error = _orientation_error(
        anchor.orientation,
        body.orientation,
    )
    stats = solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position.length() < before_position_error
    assert body.linear_velocity.x < 0.0
    assert body.angular_velocity.z < 0.0
    assert stats.fixed_joints == 1
    assert stats.velocity_impulses > 0
    assert stats.position_corrections > 0

    body.integrate_orientation(1.0 / 60.0)
    assert _orientation_error(anchor.orientation, body.orientation) < before_orientation_error


def test_fixed_joint_local_frames_can_encode_nonzero_rest_orientation() -> None:
    anchor = _static("anchor")
    rest_angle = 0.6
    body = _dynamic(
        "body",
        orientation=Quat.from_axis_angle(Vec3.axis(2), rest_angle),
    )
    joint = FixedJoint(
        "fixed",
        "anchor",
        "body",
        local_frame_b=Quat.from_axis_angle(Vec3.axis(2), -rest_angle),
    )

    ConstraintSolver(velocity_iterations=8).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.angular_velocity.length() == pytest.approx(0.0, abs=1.0e-9)


def test_fixed_joint_removes_relative_angular_velocity_at_rest_orientation() -> None:
    anchor = _static("anchor")
    body = _dynamic("body")
    body.angular_velocity = Vec3(1.0, -2.0, 3.0)

    ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (FixedJoint("fixed", "anchor", "body"),),
        dt=1.0 / 60.0,
    )

    assert body.angular_velocity.length() < 1.0e-7


def test_slider_preserves_free_axis_position_while_correcting_sideways_error() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(2.0, 1.0, -0.5))
    joint = SliderJoint("slider", "anchor", "body")
    solver = ConstraintSolver(
        velocity_iterations=12,
        position_iterations=8,
        position_correction=0.8,
    )
    before_x = body.position.x
    before_perpendicular = math.hypot(body.position.y, body.position.z)

    stats = solver.solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    after_perpendicular = math.hypot(body.position.y, body.position.z)
    assert after_perpendicular < before_perpendicular
    assert body.position.x == pytest.approx(before_x, abs=1.0e-9)
    assert stats.slider_joints == 1


def test_slider_free_axis_velocity_is_not_resisted_without_limit_or_motor() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(2.0, 0.0, 0.0))
    body.linear_velocity = Vec3(5.0, 0.0, 0.0)

    ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (SliderJoint("slider", "anchor", "body"),),
        dt=1.0 / 60.0,
    )

    assert body.linear_velocity.x == pytest.approx(5.0, abs=1.0e-9)


def test_slider_locks_twist_about_free_translation_axis() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(1.0, 0.0, 0.0))
    body.angular_velocity = Vec3(3.0, 0.0, 0.0)

    ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (SliderJoint("slider", "anchor", "body"),),
        dt=1.0 / 60.0,
    )

    assert abs(body.angular_velocity.x) < 1.0e-7


def test_slider_corrects_initial_rotational_misalignment() -> None:
    anchor = _static("anchor")
    body = _dynamic(
        "body",
        position=Vec3(1.0, 0.0, 0.0),
        orientation=Quat.from_axis_angle(Vec3.axis(2), 0.35),
    )
    joint = SliderJoint("slider", "anchor", "body", bias_factor=0.1)
    before = _orientation_error(anchor.orientation, body.orientation)

    ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )
    body.integrate_orientation(1.0 / 60.0)

    assert _orientation_error(anchor.orientation, body.orientation) < before


def test_slider_upper_stop_pulls_translation_back() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(3.0, 0.0, 0.0))
    joint = SliderJoint(
        "slider",
        "anchor",
        "body",
        lower_translation=-1.0,
        upper_translation=1.0,
        bias_factor=0.25,
    )
    before = body.position.x

    stats = ConstraintSolver(position_iterations=8).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position.x < before
    assert body.linear_velocity.x < 0.0
    assert stats.maximum_error >= 2.0


def test_slider_lower_stop_pushes_translation_forward() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(-2.0, 0.0, 0.0))
    joint = SliderJoint(
        "slider",
        "anchor",
        "body",
        lower_translation=-1.0,
        upper_translation=1.0,
        bias_factor=0.25,
    )

    ConstraintSolver(position_iterations=8).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position.x > -2.0
    assert body.linear_velocity.x > 0.0


def test_slider_motor_drives_signed_free_axis_velocity() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(1.0, 0.0, 0.0))
    joint = SliderJoint(
        "slider",
        "anchor",
        "body",
        motor_speed=4.0,
        max_motor_force=10.0,
    )

    ConstraintSolver(velocity_iterations=12).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=0.1,
    )

    assert body.linear_velocity.x > 0.0


def test_slider_motor_respects_force_impulse_budget() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(1.0, 0.0, 0.0))
    joint = SliderJoint(
        "slider",
        "anchor",
        "body",
        motor_speed=1000.0,
        max_motor_force=3.0,
    )
    dt = 0.1

    ConstraintSolver(velocity_iterations=32).solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=dt,
    )

    momentum = body.mass * abs(body.linear_velocity.x)
    assert momentum <= joint.max_motor_force * dt + 1.0e-8


def test_slider_inside_stops_is_inactive_along_free_axis() -> None:
    anchor = _static("anchor")
    body = _dynamic("body", position=Vec3(0.5, 0.0, 0.0))
    joint = SliderJoint(
        "slider",
        "anchor",
        "body",
        lower_translation=-1.0,
        upper_translation=1.0,
    )
    position = body.position

    ConstraintSolver().solve(
        {"anchor": anchor, "body": body},
        (joint,),
        dt=1.0 / 60.0,
    )

    assert body.position.x == pytest.approx(position.x, abs=1.0e-9)
    assert body.linear_velocity.x == pytest.approx(0.0, abs=1.0e-9)


def test_fixed_and_slider_parameters_bind_world_identity() -> None:
    fixed_world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    slider_world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    for world in (fixed_world, slider_world):
        world.add_body(_static("anchor"))
        world.add_body(_dynamic("body", position=Vec3(2.0, 0.0, 0.0)))

    fixed_world.add_joint(
        FixedJoint(
            "joint",
            "anchor",
            "body",
            local_anchor_a=Vec3(2.0, 0.0, 0.0),
        )
    )
    slider_world.add_joint(
        SliderJoint(
            "joint",
            "anchor",
            "body",
            upper_translation=3.0,
        )
    )

    assert fixed_world.configuration_digest != slider_world.configuration_digest
    assert fixed_world.state_digest != slider_world.state_digest


def test_world_receipt_counts_fixed_and_slider_joints() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            sleep_after_seconds=10.0,
        )
    )
    world.add_body(_static("anchor"))
    world.add_body(_dynamic("fixed-body", position=Vec3(2.0, 0.0, 0.0)))
    world.add_body(_dynamic("slider-body", position=Vec3(4.0, 0.0, 0.0)))
    world.add_joint(
        FixedJoint(
            "fixed",
            "anchor",
            "fixed-body",
            local_anchor_a=Vec3(2.0, 0.0, 0.0),
        )
    )
    world.add_joint(
        SliderJoint(
            "slider",
            "anchor",
            "slider-body",
            lower_translation=3.0,
            upper_translation=5.0,
        )
    )

    receipt = world.step()[0]
    assert receipt.constraints.fixed_joints == 1
    assert receipt.constraints.slider_joints == 1
    assert receipt.constraints.joints == 2


def test_slider_rejects_zero_axis_and_parallel_reference() -> None:
    with pytest.raises(PhysicsValidationError, match="local_axis_a"):
        SliderJoint(
            "bad-axis",
            "a",
            "b",
            local_axis_a=Vec3.zero(),
        )
    with pytest.raises(PhysicsValidationError, match="local_reference_a"):
        SliderJoint(
            "bad-reference",
            "a",
            "b",
            local_axis_a=Vec3.axis(0),
            local_reference_a=Vec3.axis(0),
        )


def test_slider_rejects_inverted_limits_and_unpaired_motor() -> None:
    with pytest.raises(PhysicsValidationError, match="upper_translation"):
        SliderJoint(
            "bad-limit",
            "a",
            "b",
            lower_translation=2.0,
            upper_translation=1.0,
        )
    with pytest.raises(PhysicsValidationError, match="requires"):
        SliderJoint(
            "bad-motor",
            "a",
            "b",
            motor_speed=1.0,
        )
    with pytest.raises(PhysicsValidationError, match="requires"):
        SliderJoint(
            "bad-force",
            "a",
            "b",
            max_motor_force=1.0,
        )


def test_fixed_joint_rejects_non_quaternion_frame() -> None:
    with pytest.raises(PhysicsValidationError, match="frames"):
        FixedJoint(
            "bad",
            "a",
            "b",
            local_frame_a="not-a-quaternion",  # type: ignore[arg-type]
        )
