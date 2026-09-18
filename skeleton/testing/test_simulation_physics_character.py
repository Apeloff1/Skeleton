"""Deterministic kinematic capsule character-controller regressions."""
from __future__ import annotations

import math

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CharacterControllerSettings,
    KinematicCharacterController,
    PhysicsSettings,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    TriangleMeshShape,
    Vec3,
    capsule_cast_world,
)


def _world() -> PhysicsWorld:
    return PhysicsWorld(
        PhysicsSettings(
            gravity=Vec3.zero(),
            sleep_after_seconds=10.0,
        )
    )


def _controller(**overrides) -> KinematicCharacterController:
    return KinematicCharacterController(
        CharacterControllerSettings(**overrides)
    )


def _floor_mesh() -> TriangleMeshShape:
    return TriangleMeshShape(
        (
            Vec3(-5.0, 0.0, -5.0),
            Vec3(5.0, 0.0, -5.0),
            Vec3(5.0, 0.0, 5.0),
            Vec3(-5.0, 0.0, 5.0),
        ),
        ((0, 2, 1), (0, 3, 2)),
    )


def test_capsule_cast_plane_returns_skin_separated_fraction() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    settings = CharacterControllerSettings()

    hit = capsule_cast_world(
        world,
        settings,
        Vec3(0.0, 1.5, 0.0),
        Vec3(0.0, -1.0, 0.0),
    )

    assert hit is not None
    assert hit.body_id == "ground"
    assert hit.normal == Vec3.axis(1)
    assert hit.fraction == pytest.approx(0.28, abs=1.0e-9)


def test_character_lands_on_plane_without_penetration_and_is_grounded() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    controller = _controller()

    result = controller.move(
        world,
        Vec3(0.0, 1.5, 0.0),
        Vec3(0.0, -1.0, 0.0),
    )

    assert result.position.y == pytest.approx(1.22, abs=1.0e-8)
    assert result.grounded
    assert result.ground_body == "ground"
    assert result.ground_normal == Vec3.axis(1)
    assert result.remaining_displacement == Vec3.zero()


def test_character_start_penetration_is_resolved_before_motion() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    controller = _controller()

    result = controller.move(
        world,
        Vec3(0.0, 1.0, 0.0),
        Vec3.zero(),
    )

    assert result.position.y == pytest.approx(1.22, abs=1.0e-8)
    assert result.actual_displacement.y == pytest.approx(0.22, abs=1.0e-8)
    assert result.grounded
    assert result.hits


def test_character_wall_slide_preserves_tangential_motion() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    world.add_body(
        RigidBody.static(
            "wall",
            PlaneShape(normal=Vec3(-1.0, 0.0, 0.0), offset=-1.0),
        )
    )
    controller = _controller()

    result = controller.move(
        world,
        Vec3(0.0, 1.22, 0.0),
        Vec3(2.0, 0.0, 1.0),
    )

    assert result.position.x == pytest.approx(0.58, abs=1.0e-7)
    assert result.position.z == pytest.approx(1.0, abs=1.0e-7)
    assert result.grounded
    assert any(hit.body_id == "wall" for hit in result.hits)


def test_walkable_slope_sets_ground_normal() -> None:
    angle = math.radians(30.0)
    normal = Vec3(0.0, math.cos(angle), -math.sin(angle))
    world = _world()
    world.add_body(
        RigidBody.static(
            "slope",
            PlaneShape(normal=normal, offset=0.0),
        )
    )
    controller = _controller(max_slope_degrees=45.0)
    start_y = 0.8 + (0.4 + 0.02) / normal.y + 0.5

    result = controller.move(
        world,
        Vec3(0.0, start_y, 0.0),
        Vec3(0.0, -1.0, 0.0),
    )

    assert result.grounded
    assert result.ground_body == "slope"
    assert result.ground_normal is not None
    assert result.ground_normal.dot(normal) > 0.999999


def test_steep_slope_is_collision_but_not_ground() -> None:
    angle = math.radians(60.0)
    normal = Vec3(0.0, math.cos(angle), -math.sin(angle))
    world = _world()
    world.add_body(
        RigidBody.static(
            "steep",
            PlaneShape(normal=normal, offset=0.0),
        )
    )
    controller = _controller(max_slope_degrees=45.0)
    start_y = 0.8 + (0.4 + 0.02) / normal.y + 0.5

    result = controller.move(
        world,
        Vec3(0.0, start_y, 0.0),
        Vec3(0.0, -1.0, 0.0),
    )

    assert any(hit.body_id == "steep" for hit in result.hits)
    assert not result.grounded


def test_character_steps_over_low_curb() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    world.add_body(
        RigidBody.static(
            "curb",
            BoxShape(Vec3(0.2, 0.125, 1.0)),
            position=Vec3(1.0, 0.125, 0.0),
        )
    )
    controller = _controller(step_height=0.3)

    result = controller.move(
        world,
        Vec3(0.0, 1.22, 0.0),
        Vec3(2.0, 0.0, 0.0),
    )

    assert result.stepped
    assert result.position.x > 1.2
    assert result.grounded


def test_character_does_not_step_through_tall_wall() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    world.add_body(
        RigidBody.static(
            "wall",
            BoxShape(Vec3(0.2, 0.6, 1.0)),
            position=Vec3(1.0, 0.6, 0.0),
        )
    )
    controller = _controller(step_height=0.3)

    result = controller.move(
        world,
        Vec3(0.0, 1.22, 0.0),
        Vec3(2.0, 0.0, 0.0),
    )

    assert not result.stepped
    assert result.position.x < 0.7
    assert result.grounded


def test_upward_jump_breaks_ground_state_without_snap_back() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    controller = _controller()

    result = controller.move(
        world,
        Vec3(0.0, 1.22, 0.0),
        Vec3(0.0, 1.0, 0.0),
    )

    assert result.position.y == pytest.approx(2.22, abs=1.0e-8)
    assert not result.grounded
    assert result.ground_body is None


def test_character_leaving_box_platform_becomes_ungrounded() -> None:
    world = _world()
    world.add_body(
        RigidBody.static(
            "platform",
            BoxShape(Vec3(1.0, 0.1, 1.0)),
            position=Vec3(0.0, -0.1, 0.0),
        )
    )
    controller = _controller()

    result = controller.move(
        world,
        Vec3(0.0, 1.22, 0.0),
        Vec3(3.0, 0.0, 0.0),
    )

    assert result.position.x > 2.0
    assert not result.grounded


def test_character_lands_on_triangle_mesh_floor() -> None:
    world = _world()
    world.add_body(RigidBody.static("terrain", _floor_mesh()))
    controller = _controller()

    result = controller.move(
        world,
        Vec3(0.2, 1.5, 0.1),
        Vec3(0.0, -1.0, 0.0),
    )

    assert result.grounded
    assert result.ground_body == "terrain"
    assert result.position.y == pytest.approx(1.22, abs=2.0e-7)
    assert any(
        hit.body_id == "terrain" and hit.triangle_index is not None
        for hit in result.hits
    )


def test_character_move_is_deterministic_for_same_world_state() -> None:
    world = _world()
    world.add_body(RigidBody.static("ground", PlaneShape()))
    world.add_body(
        RigidBody.static(
            "wall",
            PlaneShape(normal=Vec3(-1.0, 0.0, 0.0), offset=-1.0),
        )
    )
    controller = _controller()
    position = Vec3(0.0, 1.22, 0.0)
    displacement = Vec3(2.0, 0.0, 1.0)

    first = controller.move(world, position, displacement)
    second = controller.move(world, position, displacement)

    assert first == second


def test_character_policy_validation_fails_closed() -> None:
    with pytest.raises(PhysicsValidationError, match="max_slope"):
        CharacterControllerSettings(max_slope_degrees=90.0)
    with pytest.raises(PhysicsValidationError, match="radius"):
        CharacterControllerSettings(radius=0.0)
    with pytest.raises(PhysicsValidationError, match="max_iterations"):
        CharacterControllerSettings(max_iterations=0)
    with pytest.raises(PhysicsValidationError, match="cast_iterations"):
        CharacterControllerSettings(cast_iterations=0)
