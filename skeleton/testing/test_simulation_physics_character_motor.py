"""Deterministic character locomotion-motor regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CharacterControllerSettings,
    CharacterMotorSettings,
    KinematicCapsuleController,
    KinematicCharacterMotor,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    Vec3,
)


def _controller(
    *,
    position: Vec3 = Vec3(0.0, 1.02, 0.0),
) -> KinematicCapsuleController:
    return KinematicCapsuleController(
        "character",
        position=position,
        settings=CharacterControllerSettings(
            radius=0.4,
            half_height=0.6,
            skin_width=0.02,
            ground_probe_distance=0.25,
            step_height=0.35,
            max_slide_iterations=6,
            min_move_distance=1.0e-7,
        ),
    )


def _motor(**overrides) -> KinematicCharacterMotor:
    values = {
        "max_speed": 8.0,
        "ground_acceleration": 20.0,
        "air_acceleration": 8.0,
        "gravity": 10.0,
        "jump_speed": 7.0,
        "terminal_fall_speed": 25.0,
        "ground_snap_distance": 0.3,
        "support_velocity_inheritance": 1.0,
    }
    values.update(overrides)
    return KinematicCharacterMotor(
        settings=CharacterMotorSettings(**values),
    )


def _ground() -> RigidBody:
    return RigidBody.static("ground", PlaneShape())


def test_motor_settings_reject_invalid_values() -> None:
    with pytest.raises(PhysicsValidationError, match="max_speed"):
        CharacterMotorSettings(max_speed=0.0)
    with pytest.raises(PhysicsValidationError, match="gravity"):
        CharacterMotorSettings(gravity=-1.0)
    with pytest.raises(
        PhysicsValidationError,
        match="support_velocity_inheritance",
    ):
        CharacterMotorSettings(support_velocity_inheritance=1.1)


def test_ground_acceleration_moves_toward_desired_tangent_velocity() -> None:
    controller = _controller()
    motor = _motor(ground_acceleration=10.0, max_speed=20.0)

    result = motor.step(
        controller,
        Vec3(5.0, 0.0, 0.0),
        (_ground(),),
        dt=0.1,
    )

    assert result.ground_before.grounded
    assert result.velocity.x == pytest.approx(1.0, abs=1.0e-7)
    assert result.velocity.y == pytest.approx(0.0, abs=1.0e-7)
    assert controller.position.x == pytest.approx(0.1, abs=1.0e-6)
    assert motor.grounded


def test_desired_ground_speed_is_clamped_to_max_speed() -> None:
    controller = _controller()
    motor = _motor(
        max_speed=4.0,
        ground_acceleration=1000.0,
    )

    result = motor.step(
        controller,
        Vec3(100.0, 0.0, 0.0),
        (_ground(),),
        dt=0.1,
    )

    tangent = result.velocity - controller.up * result.velocity.dot(
        controller.up
    )
    assert tangent.length() == pytest.approx(4.0, abs=1.0e-7)


def test_air_control_uses_air_acceleration_and_applies_gravity() -> None:
    controller = _controller(position=Vec3(0.0, 5.0, 0.0))
    motor = _motor(
        air_acceleration=2.0,
        gravity=10.0,
        terminal_fall_speed=50.0,
    )

    result = motor.step(
        controller,
        Vec3(8.0, 0.0, 0.0),
        (),
        dt=0.5,
    )

    assert not result.ground_before.grounded
    assert result.velocity.x == pytest.approx(1.0, abs=1.0e-7)
    assert result.velocity.y == pytest.approx(-5.0, abs=1.0e-7)
    assert not motor.grounded


def test_terminal_fall_speed_is_hard_bounded() -> None:
    controller = _controller(position=Vec3(0.0, 100.0, 0.0))
    motor = KinematicCharacterMotor(
        velocity=Vec3(0.0, -20.0, 0.0),
        settings=CharacterMotorSettings(
            max_speed=8.0,
            ground_acceleration=20.0,
            air_acceleration=8.0,
            gravity=50.0,
            jump_speed=7.0,
            terminal_fall_speed=22.0,
            ground_snap_distance=0.3,
        ),
    )

    result = motor.step(
        controller,
        Vec3.zero(),
        (),
        dt=1.0,
    )

    assert result.velocity.y == pytest.approx(-22.0, abs=1.0e-7)


def test_grounded_jump_sets_upward_speed_and_leaves_support() -> None:
    controller = _controller()
    motor = _motor(jump_speed=7.5)

    result = motor.step(
        controller,
        Vec3.zero(),
        (_ground(),),
        dt=0.1,
        jump=True,
    )

    assert result.jumped
    assert result.velocity.y == pytest.approx(7.5, abs=1.0e-6)
    assert not motor.grounded
    assert motor.support_body_id is None
    assert controller.position.y > 1.5


def test_jump_request_in_air_does_not_double_jump() -> None:
    controller = _controller(position=Vec3(0.0, 5.0, 0.0))
    motor = KinematicCharacterMotor(
        velocity=Vec3(0.0, 3.0, 0.0),
        settings=_motor().settings,
    )

    result = motor.step(
        controller,
        Vec3.zero(),
        (),
        dt=0.1,
        jump=True,
    )

    assert not result.jumped
    assert result.velocity.y < 3.0


def test_moving_platform_velocity_is_inherited_without_input() -> None:
    controller = _controller()
    platform = RigidBody.kinematic(
        "platform",
        PlaneShape(),
        linear_velocity=Vec3(2.0, 0.0, 0.0),
    )
    motor = _motor()

    first = motor.step(
        controller,
        Vec3.zero(),
        (platform,),
        dt=0.1,
    )
    second = motor.step(
        controller,
        Vec3.zero(),
        (platform,),
        dt=0.1,
    )

    assert first.velocity.x == pytest.approx(2.0, abs=1.0e-7)
    assert second.velocity.x == pytest.approx(2.0, abs=1.0e-7)
    assert controller.position.x == pytest.approx(0.4, abs=1.0e-5)
    assert motor.support_body_id == "platform"
    assert motor.support_velocity.x == pytest.approx(2.0)


def test_platform_inheritance_factor_scales_support_velocity() -> None:
    controller = _controller()
    platform = RigidBody.kinematic(
        "platform",
        PlaneShape(),
        linear_velocity=Vec3(4.0, 0.0, 0.0),
    )
    motor = _motor(support_velocity_inheritance=0.5)

    result = motor.step(
        controller,
        Vec3.zero(),
        (platform,),
        dt=0.1,
    )

    assert result.velocity.x == pytest.approx(2.0, abs=1.0e-7)
    assert result.support_velocity.x == pytest.approx(2.0, abs=1.0e-7)


def test_wall_contact_clips_inward_velocity_and_preserves_tangent() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 3.0)),
        position=Vec3(1.5, 1.0, 0.0),
    )
    motor = KinematicCharacterMotor(
        velocity=Vec3(5.0, 0.0, 2.0),
        settings=CharacterMotorSettings(
            max_speed=10.0,
            ground_acceleration=100.0,
            air_acceleration=20.0,
            gravity=10.0,
            jump_speed=7.0,
            terminal_fall_speed=25.0,
            ground_snap_distance=0.3,
        ),
    )

    result = motor.step(
        controller,
        Vec3(5.0, 0.0, 2.0),
        (_ground(), wall),
        dt=0.5,
    )

    assert result.move.hits
    assert result.velocity.x <= 1.0e-6
    assert result.velocity.z > 1.5
    assert controller.position.z > 0.5


def test_ground_snap_settles_small_gap_to_skin_width() -> None:
    controller = _controller(position=Vec3(0.0, 1.10, 0.0))
    motor = _motor()

    result = motor.step(
        controller,
        Vec3.zero(),
        (_ground(),),
        dt=0.1,
    )

    assert result.ground_after.grounded
    assert result.snapped_distance == pytest.approx(0.08, abs=3.0e-4)
    assert controller.position.y == pytest.approx(1.02, abs=3.0e-4)


def test_motor_target_order_is_deterministic() -> None:
    ground = _ground()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 3.0)),
        position=Vec3(1.5, 1.0, 0.0),
    )
    controller_a = _controller()
    controller_b = _controller()
    motor_a = _motor(ground_acceleration=100.0)
    motor_b = _motor(ground_acceleration=100.0)

    first = motor_a.step(
        controller_a,
        Vec3(6.0, 0.0, 2.0),
        (ground, wall),
        dt=0.5,
    )
    second = motor_b.step(
        controller_b,
        Vec3(6.0, 0.0, 2.0),
        (wall, ground),
        dt=0.5,
    )

    assert first == second
    assert controller_a.position == controller_b.position


def test_world_character_motor_wrapper_uses_world_bodies_and_default_dt() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.1,
        )
    )
    world.add_body(_ground())
    controller = _controller()
    motor = _motor(ground_acceleration=10.0)

    result = world.step_character_motor(
        controller,
        motor,
        Vec3(5.0, 0.0, 0.0),
    )

    assert result.velocity.x == pytest.approx(1.0, abs=1.0e-7)
    assert controller.position.x == pytest.approx(0.1, abs=1.0e-6)


def test_world_character_motor_wrapper_rejects_wrong_motor() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    controller = _controller()

    with pytest.raises(PhysicsValidationError, match="motor"):
        world.step_character_motor(  # type: ignore[arg-type]
            controller,
            object(),
            Vec3.zero(),
        )
