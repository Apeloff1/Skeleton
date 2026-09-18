"""Kinematic capsule controller movement, slide, ground, and step regressions."""
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


def _floor(body_id: str = "floor") -> RigidBody:
    return RigidBody.static(body_id, PlaneShape())


def _wall(
    body_id: str = "wall",
    *,
    x: float = 1.0,
    half_height: float = 2.0,
) -> RigidBody:
    return RigidBody.static(
        body_id,
        BoxShape(Vec3(0.1, half_height, 5.0)),
        position=Vec3(x, half_height, 0.0),
    )


def _controller(
    position: Vec3 = Vec3(0.0, 1.22, 0.0),
    *,
    settings: CharacterControllerSettings | None = None,
) -> KinematicCapsuleController:
    return KinematicCapsuleController(
        position=position,
        settings=settings or CharacterControllerSettings(),
    )


def test_character_moves_freely_without_obstacles() -> None:
    controller = _controller(Vec3.zero())

    result = controller.move(Vec3(1.0, 2.0, -3.0), ())

    assert result.position == Vec3(1.0, 2.0, -3.0)
    assert result.applied_displacement == Vec3(1.0, 2.0, -3.0)
    assert result.remaining_displacement == Vec3.zero()
    assert not result.hits
    assert not result.grounded


def test_character_stops_at_tall_wall_with_skin_width() -> None:
    settings = CharacterControllerSettings(step_height=0.0)
    controller = _controller(settings=settings)

    result = controller.move(Vec3(2.0, 0.0, 0.0), (_wall(),))

    assert result.position.x < 0.55
    assert result.position.x > 0.40
    assert result.hits
    assert result.hits[0].body_id == "wall"
    assert result.hits[0].normal.x < -0.999
    assert not result.stepped


def test_character_slides_tangentially_along_wall() -> None:
    settings = CharacterControllerSettings(step_height=0.0)
    controller = _controller(settings=settings)

    result = controller.move(Vec3(2.0, 0.0, 1.0), (_wall(),))

    assert result.position.x < 0.55
    assert result.position.z > 0.9
    assert result.applied_displacement.z > 0.9
    assert len(result.hits) >= 1


def test_ground_probe_finds_walkable_floor_and_snap_is_deterministic() -> None:
    controller = _controller(Vec3(0.0, 1.27, 0.0))
    floor = _floor()

    hit = controller.probe_ground((floor,))

    assert hit is not None
    assert hit.walkable
    assert hit.normal == Vec3.axis(1)
    assert hit.distance == pytest.approx(0.05, abs=2.0e-6)

    result = controller.move(Vec3.zero(), (floor,))
    assert result.grounded
    assert result.ground_normal == Vec3.axis(1)
    assert result.position.y == pytest.approx(1.22, abs=2.0e-6)


def test_downward_character_motion_lands_on_floor() -> None:
    controller = _controller(Vec3(0.0, 2.0, 0.0))

    result = controller.move(Vec3(0.0, -2.0, 0.0), (_floor(),))

    assert result.grounded
    assert result.position.y == pytest.approx(1.22, abs=2.0e-6)
    assert result.ground_normal == Vec3.axis(1)
    assert result.hits[0].walkable


def test_low_obstacle_uses_bounded_step_up_and_lands_on_top() -> None:
    controller = _controller()
    floor = _floor()
    step = RigidBody.static(
        "step",
        BoxShape(Vec3(0.25, 0.1, 1.0)),
        position=Vec3(0.8, 0.1, 0.0),
    )

    result = controller.move(
        Vec3(1.0, 0.0, 0.0),
        (floor, step),
    )

    assert result.stepped
    assert result.grounded
    assert result.position.x == pytest.approx(1.0, abs=2.0e-5)
    assert result.position.y > 1.35
    assert result.position.y < 1.50
    assert any(hit.body_id == "step" for hit in result.hits)


def test_tall_obstacle_is_not_misclassified_as_step() -> None:
    controller = _controller()
    floor = _floor()
    obstacle = RigidBody.static(
        "tall",
        BoxShape(Vec3(0.25, 0.5, 1.0)),
        position=Vec3(0.8, 0.5, 0.0),
    )

    result = controller.move(
        Vec3(1.0, 0.0, 0.0),
        (floor, obstacle),
    )

    assert not result.stepped
    assert result.position.x < 0.3


@pytest.mark.parametrize(
    ("degrees", "expected_walkable"),
    (
        (30.0, True),
        (60.0, False),
    ),
)
def test_slope_classification_uses_configured_walkable_angle(
    degrees: float,
    expected_walkable: bool,
) -> None:
    rotation = Quat.from_axis_angle(
        Vec3.axis(2),
        math.radians(degrees),
    )
    plane = RigidBody.static(
        "slope",
        PlaneShape(),
        orientation=rotation,
    )
    normal, _ = plane.shape.world_equation(plane.transform)
    settings = CharacterControllerSettings(max_slope_degrees=50.0)
    extent = (
        settings.half_height * abs(normal.dot(Vec3.axis(1)))
        + settings.radius
        + settings.skin_width
    )
    controller = _controller(
        normal * (extent + 0.05),
        settings=settings,
    )

    hit = controller.sweep(-normal * 0.2, (plane,))

    assert hit is not None
    assert hit.walkable is expected_walkable


def test_character_motion_is_order_invariant_for_world_body_input() -> None:
    bodies = (_floor(), _wall())
    left = _controller()
    right = _controller()

    first = left.move(Vec3(2.0, -0.1, 1.0), bodies)
    second = right.move(
        Vec3(2.0, -0.1, 1.0),
        tuple(reversed(bodies)),
    )

    assert first == second
    assert left.position == right.position


def test_character_sweep_rejects_reserved_query_body_id_collision() -> None:
    controller = _controller()
    obstacle = RigidBody.static(
        "character.query",
        BoxShape(Vec3.one()),
        position=Vec3(2.0, 0.0, 0.0),
    )

    with pytest.raises(PhysicsValidationError, match="reserved"):
        controller.sweep(Vec3(1.0, 0.0, 0.0), (obstacle,))


def test_character_settings_validate_slope_slide_and_distance_bounds() -> None:
    with pytest.raises(PhysicsValidationError, match="max_slope_degrees"):
        CharacterControllerSettings(max_slope_degrees=90.0)
    with pytest.raises(PhysicsValidationError, match="max_slides"):
        CharacterControllerSettings(max_slides=0)
    with pytest.raises(PhysicsValidationError, match="min_move_distance"):
        CharacterControllerSettings(min_move_distance=0.0)


def test_character_orientation_defines_controller_up_axis() -> None:
    controller = KinematicCapsuleController(
        position=Vec3.zero(),
        orientation=Quat.from_axis_angle(
            Vec3.axis(2),
            -math.pi * 0.5,
        ),
    )

    assert controller.up.x > 0.999999
    assert abs(controller.up.y) < 1.0e-9
