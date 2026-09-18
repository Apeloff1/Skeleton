"""Deterministic kinematic capsule character-controller regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CharacterControllerSettings,
    KinematicCapsuleController,
    PhysicsValidationError,
    PlaneShape,
    Quat,
    RigidBody,
    Vec3,
)


def _settings(**overrides) -> CharacterControllerSettings:
    values = {
        "radius": 0.4,
        "half_height": 0.6,
        "skin_width": 0.02,
        "max_slope_angle": math.radians(50.0),
        "step_height": 0.4,
        "ground_probe_distance": 0.25,
        "max_slide_iterations": 6,
        "min_move_distance": 1.0e-7,
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


def test_character_settings_fail_closed_on_invalid_geometry_and_limits() -> None:
    with pytest.raises(PhysicsValidationError, match="radius"):
        CharacterControllerSettings(radius=0.0)
    with pytest.raises(PhysicsValidationError, match="half_height"):
        CharacterControllerSettings(half_height=-1.0)
    with pytest.raises(PhysicsValidationError, match="max_slope_angle"):
        CharacterControllerSettings(max_slope_angle=math.pi * 0.5)
    with pytest.raises(PhysicsValidationError, match="max_slide_iterations"):
        CharacterControllerSettings(max_slide_iterations=0)


def test_controller_reuses_strict_rigid_body_id_validation() -> None:
    with pytest.raises(PhysicsValidationError, match="body_id"):
        KinematicCapsuleController(" bad id ")


def test_capsule_sweep_hits_plane_at_exact_capsule_support_distance() -> None:
    controller = _controller(position=Vec3(0.0, 2.0, 0.0))
    plane = RigidBody.static("ground", PlaneShape())

    hit = controller.sweep(
        Vec3(0.0, -2.0, 0.0),
        (plane,),
        dt=1.0,
    )

    assert hit is not None
    assert hit.body_id == "ground"
    assert hit.fraction == pytest.approx(0.5, abs=2.0e-6)
    assert hit.distance == pytest.approx(1.0, abs=2.0e-6)
    assert hit.normal.almost_equal(Vec3.axis(1), tolerance=1.0e-8)


def test_ground_probe_detects_flat_walkable_plane() -> None:
    controller = _controller(position=Vec3(0.0, 1.05, 0.0))
    plane = RigidBody.static("ground", PlaneShape())

    ground = controller.ground_probe((plane,), dt=1.0)

    assert ground.grounded
    assert ground.body_id == "ground"
    assert ground.distance == pytest.approx(0.05, abs=2.0e-6)
    assert ground.slope_angle == pytest.approx(0.0, abs=1.0e-8)
    assert ground.normal.almost_equal(Vec3.axis(1), tolerance=1.0e-8)


def test_ground_probe_rejects_surface_above_slope_limit() -> None:
    controller = _controller(position=Vec3(0.0, 1.0, 0.0))
    steep = RigidBody.static(
        "steep",
        PlaneShape(),
        orientation=Quat.from_axis_angle(
            Vec3.axis(2),
            math.radians(65.0),
        ),
    )

    ground = controller.ground_probe(
        (steep,),
        dt=1.0,
        distance=1.0,
    )

    assert not ground.grounded
    assert ground.body_id is None


def test_walkable_classification_matches_configured_slope_angle() -> None:
    controller = _controller()
    thirty = Vec3(
        math.sin(math.radians(30.0)),
        math.cos(math.radians(30.0)),
        0.0,
    )
    sixty = Vec3(
        math.sin(math.radians(60.0)),
        math.cos(math.radians(60.0)),
        0.0,
    )

    assert controller.is_walkable(thirty)
    assert not controller.is_walkable(sixty)


def test_free_space_move_applies_entire_requested_displacement() -> None:
    controller = _controller()
    displacement = Vec3(1.25, 0.2, -0.5)

    result = controller.move(displacement, (), dt=1.0 / 60.0)

    assert result.position == Vec3(1.25, 1.2, -0.5)
    assert result.applied_displacement == displacement
    assert result.remaining_displacement == Vec3.zero()
    assert result.hits == ()
    assert not result.stepped


def test_character_stops_at_skin_width_before_wall() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(2.0, 1.0, 0.0),
    )

    result = controller.move(
        Vec3(3.0, 0.0, 0.0),
        (wall,),
        dt=1.0,
    )

    # Wall left face is x=1.75 and capsule radius is 0.4, so exact contact
    # center is x=1.35. Controller stops one skin width short.
    assert result.position.x == pytest.approx(1.33, abs=3.0e-3)
    assert result.hits
    assert result.hits[0].body_id == "wall"
    assert result.hits[0].normal.x < -0.999
    assert result.remaining_displacement.length() <= 1.0e-6


def test_diagonal_move_slides_along_wall_without_losing_tangent_motion() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 5.0)),
        position=Vec3(2.0, 1.0, 0.0),
    )

    result = controller.move(
        Vec3(3.0, 0.0, 1.0),
        (wall,),
        dt=1.0,
    )

    assert 1.30 < result.position.x < 1.35
    assert result.position.z > 0.9
    assert result.hits
    assert result.remaining_displacement.length() <= 1.0e-5


def test_ignore_mask_allows_character_to_pass_through_named_body() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(2.0, 1.0, 0.0),
    )

    result = controller.move(
        Vec3(3.0, 0.0, 0.0),
        (wall,),
        dt=1.0,
        ignore=("wall",),
    )

    assert result.position.x == pytest.approx(3.0)
    assert result.hits == ()


def test_low_obstacle_uses_bounded_up_forward_down_step_sequence() -> None:
    controller = _controller()
    ground = RigidBody.static("ground", PlaneShape())
    step = RigidBody.static(
        "step",
        BoxShape(Vec3(0.25, 0.15, 1.0)),
        position=Vec3(0.8, 0.15, 0.0),
    )

    result = controller.move(
        Vec3(1.0, 0.0, 0.0),
        (step, ground),
        dt=1.0,
    )

    assert result.stepped
    assert result.position.x > 0.95
    # Step top is y=0.3; capsule bottom is one unit below center and skin is
    # retained above the landing surface.
    assert result.position.y == pytest.approx(1.32, abs=3.0e-2)
    assert result.ground.grounded
    assert result.ground.body_id == "step"


def test_obstacle_taller_than_step_budget_is_not_climbed() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 0.75, 1.0)),
        position=Vec3(0.8, 0.75, 0.0),
    )
    ground = RigidBody.static("ground", PlaneShape())

    result = controller.move(
        Vec3(1.5, 0.0, 0.0),
        (wall, ground),
        dt=1.0,
    )

    assert not result.stepped
    assert result.position.x < 0.5


def test_target_order_does_not_change_character_result() -> None:
    ground = RigidBody.static("ground", PlaneShape())
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(2.0, 1.0, 0.0),
    )
    left = _controller()
    right = _controller()

    first = left.move(
        Vec3(3.0, 0.0, 0.75),
        (ground, wall),
        dt=1.0,
    )
    second = right.move(
        Vec3(3.0, 0.0, 0.75),
        (wall, ground),
        dt=1.0,
    )

    assert first == second


def test_controller_supports_non_y_up_orientation() -> None:
    controller = _controller(
        position=Vec3(0.0, 0.0, 1.05),
        up=Vec3.axis(2),
    )
    plane = RigidBody.static(
        "ground",
        PlaneShape(),
        orientation=Quat.from_axis_angle(
            Vec3.axis(0),
            math.pi * 0.5,
        ),
    )

    ground = controller.ground_probe((plane,), dt=1.0)

    assert ground.grounded
    assert ground.normal.almost_equal(Vec3.axis(2), tolerance=1.0e-8)
    assert ground.distance == pytest.approx(0.05, abs=2.0e-6)


def test_zero_distance_ground_probe_is_explicitly_not_grounded() -> None:
    controller = _controller()

    ground = controller.ground_probe(
        (),
        dt=1.0,
        distance=0.0,
    )

    assert not ground.grounded
    assert ground.distance == 0.0


def test_initial_overlap_moving_out_is_not_treated_as_blocking_sweep() -> None:
    controller = _controller(position=Vec3(1.5, 1.0, 0.0))
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(2.0, 1.0, 0.0),
    )

    hit = controller.sweep(
        Vec3(-1.0, 0.0, 0.0),
        (wall,),
        dt=1.0,
    )

    assert hit is None


def test_move_result_applied_displacement_matches_position_delta() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(2.0, 1.0, 0.0),
    )

    result = controller.move(
        Vec3(3.0, 0.0, 0.5),
        (wall,),
        dt=1.0,
    )

    assert result.applied_displacement == (
        result.position - result.start_position
    )
