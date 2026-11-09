"""Advanced kinematic character runtime regressions.

Covers overlap recovery, capsule resizing/headroom, moving-platform support
velocity, deterministic carry, and PhysicsWorld runtime wrappers.
"""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CharacterControllerSettings,
    CharacterRecoveryResult,
    CharacterResizeResult,
    CharacterRuntimeResult,
    KinematicCapsuleController,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    Quat,
    RigidBody,
    Vec3,
    detect_collision,
)


def _settings(**overrides) -> CharacterControllerSettings:
    values = {
        "radius": 0.4,
        "half_height": 0.6,
        "skin_width": 0.02,
        "max_slope_angle": math.radians(50.0),
        "step_height": 0.35,
        "ground_probe_distance": 0.25,
        "max_slide_iterations": 6,
        "min_move_distance": 1.0e-7,
        "max_recovery_iterations": 8,
        "max_recovery_distance": 2.0,
    }
    values.update(overrides)
    return CharacterControllerSettings(**values)


def _controller(
    *,
    position: Vec3 = Vec3(0.0, 1.0, 0.0),
    up: Vec3 = Vec3.axis(1),
    settings: CharacterControllerSettings | None = None,
) -> KinematicCapsuleController:
    return KinematicCapsuleController(
        "character",
        position=position,
        up=up,
        settings=_settings() if settings is None else settings,
    )


def _platform(
    *,
    body_id: str = "platform",
    position: Vec3 = Vec3.zero(),
    linear_velocity: Vec3 = Vec3.zero(),
    angular_velocity: Vec3 = Vec3.zero(),
) -> RigidBody:
    return RigidBody.kinematic(
        body_id,
        BoxShape(Vec3(2.0, 0.1, 2.0)),
        position=position,
        linear_velocity=linear_velocity,
        angular_velocity=angular_velocity,
    )


def _probe_body(controller: KinematicCapsuleController) -> RigidBody:
    return RigidBody.kinematic(
        "probe",
        controller.shape,
        position=controller.position,
        orientation=controller.orientation,
    )


def test_advanced_character_settings_validate_recovery_bounds() -> None:
    with pytest.raises(PhysicsValidationError, match="max_recovery_iterations"):
        _settings(max_recovery_iterations=0)
    with pytest.raises(PhysicsValidationError, match="max_recovery_distance"):
        _settings(max_recovery_distance=0.0)


def test_overlap_recovery_pushes_character_out_without_mutating_scene_body() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(0.5, 1.0, 0.0),
    )
    wall_position = wall.position
    wall_orientation = wall.orientation

    before = detect_collision(_probe_body(controller), wall)
    assert before is not None
    assert before.penetration > 0.0

    result = controller.recover_overlaps((wall,))

    assert isinstance(result, CharacterRecoveryResult)
    assert result.recovered
    assert result.iterations >= 1
    assert result.body_ids[0] == "wall"
    assert controller.position.x < 0.0
    assert result.displacement == result.position - result.start_position
    after = detect_collision(_probe_body(controller), wall)
    assert after is None or after.penetration <= 1.0e-8
    assert wall.position == wall_position
    assert wall.orientation == wall_orientation


def test_overlap_recovery_is_noop_when_character_is_clear() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(5.0, 1.0, 0.0),
    )

    result = controller.recover_overlaps((wall,))

    assert not result.recovered
    assert result.iterations == 0
    assert result.displacement == Vec3.zero()
    assert result.body_ids == ()
    assert controller.position == Vec3(0.0, 1.0, 0.0)


def test_overlap_recovery_respects_ignore_mask() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(0.5, 1.0, 0.0),
    )

    result = controller.recover_overlaps((wall,), ignore=("wall",))

    assert not result.recovered
    assert controller.position == Vec3(0.0, 1.0, 0.0)


def test_overlap_recovery_distance_bound_fails_closed() -> None:
    controller = _controller(
        position=Vec3(0.0, 0.8, 0.0),
        settings=_settings(max_recovery_distance=0.05),
    )
    ground = RigidBody.static("ground", PlaneShape())

    with pytest.raises(
        PhysicsValidationError,
        match="recovery distance bound",
    ):
        controller.recover_overlaps((ground,))


def test_overlap_recovery_supports_non_y_up_plane() -> None:
    controller = _controller(
        position=Vec3(0.0, 0.0, 0.8),
        up=Vec3.axis(2),
    )
    plane = RigidBody.static(
        "ground",
        PlaneShape(),
        orientation=Quat.from_axis_angle(Vec3.axis(0), math.pi * 0.5),
    )

    result = controller.recover_overlaps((plane,))

    assert result.recovered
    assert controller.position.z > 0.8


def test_crouch_resize_preserves_capsule_foot_position() -> None:
    controller = _controller(position=Vec3(0.0, 1.0, 0.0))
    old_foot = (
        controller.position
        - controller.up
        * (controller.settings.half_height + controller.settings.radius)
    )

    result = controller.resize(0.3, ())

    assert isinstance(result, CharacterResizeResult)
    assert result.changed
    assert controller.settings.half_height == pytest.approx(0.3)
    assert controller.position.y == pytest.approx(0.7)
    new_foot = (
        controller.position
        - controller.up
        * (controller.settings.half_height + controller.settings.radius)
    )
    assert new_foot.almost_equal(old_foot, tolerance=1.0e-12)


def test_stand_resize_preserves_foot_and_restores_height() -> None:
    controller = _controller(
        position=Vec3(0.0, 0.7, 0.0),
        settings=_settings(half_height=0.3),
    )

    result = controller.resize(0.6, ())

    assert result.changed
    assert not result.blocked_by
    assert controller.settings.half_height == pytest.approx(0.6)
    assert controller.position.y == pytest.approx(1.0)


def test_resize_can_keep_center_fixed_when_requested() -> None:
    controller = _controller(position=Vec3(0.0, 1.0, 0.0))

    result = controller.resize(
        0.3,
        (),
        preserve_foot=False,
    )

    assert result.changed
    assert controller.position == Vec3(0.0, 1.0, 0.0)
    assert controller.settings.half_height == pytest.approx(0.3)


def test_blocked_headroom_prevents_standing_without_mutation() -> None:
    controller = _controller(
        position=Vec3(0.0, 0.7, 0.0),
        settings=_settings(half_height=0.3),
    )
    ceiling = RigidBody.static(
        "ceiling",
        BoxShape(Vec3(2.0, 0.1, 2.0)),
        position=Vec3(0.0, 1.55, 0.0),
    )
    before_position = controller.position
    before_settings = controller.settings

    result = controller.resize(0.6, (ceiling,))

    assert not result.changed
    assert result.blocked_by == ("ceiling",)
    assert controller.position == before_position
    assert controller.settings == before_settings


def test_resize_ignore_mask_can_explicitly_bypass_headroom_body() -> None:
    controller = _controller(
        position=Vec3(0.0, 0.7, 0.0),
        settings=_settings(half_height=0.3),
    )
    ceiling = RigidBody.static(
        "ceiling",
        BoxShape(Vec3(2.0, 0.1, 2.0)),
        position=Vec3(0.0, 1.55, 0.0),
    )

    result = controller.resize(
        0.6,
        (ceiling,),
        ignore=("ceiling",),
    )

    assert result.changed
    assert result.blocked_by == ()
    assert controller.position.y == pytest.approx(1.0)


def test_same_height_resize_is_explicit_noop() -> None:
    controller = _controller()

    result = controller.resize(0.6, ())

    assert not result.changed
    assert result.blocked_by == ()
    assert controller.position == Vec3(0.0, 1.0, 0.0)


def test_ground_support_velocity_matches_platform_point_velocity() -> None:
    controller = _controller(position=Vec3(1.0, 1.12, 0.0))
    platform = _platform(
        linear_velocity=Vec3(2.0, 0.0, 0.0),
        angular_velocity=Vec3(0.0, 0.0, 0.5),
    )
    ground = controller.ground_probe((platform,), dt=0.25)

    assert ground.grounded
    velocity = controller.support_velocity(ground, (platform,))
    expected = platform.velocity_at_world_point(ground.point)

    assert velocity.almost_equal(expected, tolerance=1.0e-10)


def test_ungrounded_character_has_zero_support_velocity() -> None:
    controller = _controller(position=Vec3(0.0, 5.0, 0.0))
    platform = _platform()
    ground = controller.ground_probe((platform,), dt=0.1)

    assert not ground.grounded
    assert controller.support_velocity(ground, (platform,)) == Vec3.zero()


def test_runtime_step_carries_character_with_translating_platform() -> None:
    controller = _controller(position=Vec3(0.0, 1.12, 0.0))
    platform = _platform(linear_velocity=Vec3(2.0, 0.0, 0.0))

    result = controller.runtime_step(
        Vec3.zero(),
        (platform,),
        dt=0.25,
    )

    assert isinstance(result, CharacterRuntimeResult)
    assert result.support_velocity.x == pytest.approx(2.0)
    assert result.carry_displacement.x == pytest.approx(0.5)
    assert result.input_displacement == Vec3.zero()
    assert controller.position.x == pytest.approx(0.5, abs=2.0e-5)
    assert result.applied_displacement.x == pytest.approx(0.5, abs=2.0e-5)


def test_runtime_step_combines_platform_carry_and_player_velocity() -> None:
    controller = _controller(position=Vec3(0.0, 1.12, 0.0))
    platform = _platform(linear_velocity=Vec3(2.0, 0.0, 0.0))

    result = controller.runtime_step(
        Vec3(0.0, 0.0, 4.0),
        (platform,),
        dt=0.25,
    )

    assert result.carry_displacement.x == pytest.approx(0.5)
    assert result.input_displacement.z == pytest.approx(1.0)
    assert controller.position.x == pytest.approx(0.5, abs=2.0e-5)
    assert controller.position.z == pytest.approx(1.0, abs=2.0e-5)


def test_runtime_support_carry_can_be_disabled() -> None:
    controller = _controller(position=Vec3(0.0, 1.12, 0.0))
    platform = _platform(linear_velocity=Vec3(2.0, 0.0, 0.0))

    result = controller.runtime_step(
        Vec3.zero(),
        (platform,),
        dt=0.25,
        carry_support=False,
    )

    assert result.support_velocity == Vec3.zero()
    assert result.carry_displacement == Vec3.zero()
    assert controller.position.x == pytest.approx(0.0)


def test_runtime_step_recovers_initial_overlap_before_player_move() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(0.5, 1.0, 0.0),
    )

    result = controller.runtime_step(
        Vec3(0.0, 0.0, 1.0),
        (wall,),
        dt=0.1,
    )

    assert result.recovery.recovered
    assert result.recovery.displacement.x < 0.0
    assert controller.position.z > 0.09


def test_runtime_step_can_leave_overlap_recovery_disabled() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(0.5, 1.0, 0.0),
    )

    result = controller.runtime_step(
        Vec3.zero(),
        (wall,),
        dt=0.1,
        recover_overlaps=False,
    )

    assert not result.recovery.recovered
    assert result.recovery.displacement == Vec3.zero()


def test_runtime_result_applied_displacement_includes_recovery_and_motion() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(0.5, 1.0, 0.0),
    )

    result = controller.runtime_step(
        Vec3(0.0, 0.0, 2.0),
        (wall,),
        dt=0.1,
    )

    assert result.applied_displacement == result.position - result.start_position
    assert result.position == controller.position


def test_world_recovery_wrapper_uses_authoritative_bodies() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(0.5, 1.0, 0.0),
    )
    world.add_body(wall)
    controller = _controller()

    result = world.recover_character_overlaps(controller)

    assert result.recovered
    assert controller.position.x < 0.0


def test_world_resize_wrapper_enforces_headroom() -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    ceiling = RigidBody.static(
        "ceiling",
        BoxShape(Vec3(2.0, 0.1, 2.0)),
        position=Vec3(0.0, 1.55, 0.0),
    )
    world.add_body(ceiling)
    controller = _controller(
        position=Vec3(0.0, 0.7, 0.0),
        settings=_settings(half_height=0.3),
    )

    result = world.resize_character(controller, 0.6)

    assert not result.changed
    assert result.blocked_by == ("ceiling",)
    assert controller.settings.half_height == pytest.approx(0.3)


def test_world_runtime_wrapper_uses_default_fixed_dt() -> None:
    world = PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            fixed_dt=0.25,
        )
    )
    platform = _platform(linear_velocity=Vec3(2.0, 0.0, 0.0))
    world.add_body(platform)
    controller = _controller(position=Vec3(0.0, 1.12, 0.0))

    result = world.step_character_runtime(
        controller,
        Vec3.zero(),
    )

    assert result.carry_displacement.x == pytest.approx(0.5)
    assert controller.position.x == pytest.approx(0.5, abs=2.0e-5)


@pytest.mark.parametrize(
    "method",
    (
        "recover_character_overlaps",
        "resize_character",
        "step_character_runtime",
    ),
)
def test_advanced_world_character_wrappers_reject_wrong_controller_type(
    method: str,
) -> None:
    world = PhysicsWorld(PhysicsSettings(gravity=Vec3.zero()))
    function = getattr(world, method)

    with pytest.raises(PhysicsValidationError, match="controller"):
        if method == "resize_character":
            function(object(), 0.3)
        elif method == "step_character_runtime":
            function(object(), Vec3.zero())
        else:
            function(object())
