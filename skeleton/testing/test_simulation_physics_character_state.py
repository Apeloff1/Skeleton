"""Character controller snapshot and restore regressions."""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

from skeleton.simulation.physics import (
    BoxShape,
    CharacterControllerSettings,
    CharacterControllerState,
    KinematicCapsuleController,
    PhysicsSnapshotError,
    PhysicsValidationError,
    RigidBody,
    Vec3,
    build_character_state,
    verify_character_state,
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
    body_id: str = "character",
    *,
    position: Vec3 = Vec3(0.0, 1.0, 0.0),
    up: Vec3 = Vec3.axis(1),
    settings: CharacterControllerSettings | None = None,
) -> KinematicCapsuleController:
    return KinematicCapsuleController(
        body_id,
        position=position,
        up=up,
        settings=_settings() if settings is None else settings,
    )


def test_character_state_capture_is_deterministic() -> None:
    controller = _controller()

    first = controller.capture_state()
    second = controller.capture_state()

    assert first == second
    assert first.state_digest == controller.state_digest
    assert verify_character_state(first) is first


def test_build_character_state_normalizes_up_before_hashing() -> None:
    state = build_character_state(
        body_id="character",
        position=Vec3(1.0, 2.0, 3.0),
        up=Vec3(0.0, 2.0, 0.0),
        settings=_settings(),
    )

    assert state.up == Vec3.axis(1)
    assert verify_character_state(state) == state


def test_character_state_digest_changes_with_position() -> None:
    controller = _controller()
    before = controller.state_digest

    controller.position = controller.position + Vec3(0.25, -0.1, 0.5)

    assert controller.state_digest != before


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("radius", 0.45),
        ("half_height", 0.7),
        ("skin_width", 0.03),
        ("max_slope_angle", math.radians(40.0)),
        ("step_height", 0.45),
        ("ground_probe_distance", 0.35),
        ("max_slide_iterations", 7),
        ("min_move_distance", 2.0e-7),
        ("max_recovery_iterations", 9),
        ("max_recovery_distance", 3.0),
    ),
)
def test_every_future_affecting_setting_is_bound_into_character_digest(
    field: str,
    value: float | int,
) -> None:
    baseline = _controller()
    changed = _controller(
        settings=replace(baseline.settings, **{field: value}),
    )

    assert baseline.state_digest != changed.state_digest


def test_character_state_digest_changes_with_up_axis() -> None:
    left = _controller(up=Vec3.axis(1))
    right = _controller(up=Vec3.axis(2))

    assert left.state_digest != right.state_digest


def test_restore_round_trip_recovers_position_up_and_resized_settings() -> None:
    controller = _controller()
    original = controller.capture_state()

    resize = controller.resize(0.3, ())
    assert resize.changed
    controller.position = Vec3(9.0, -2.0, 4.0)
    controller.up = Vec3.axis(2)
    controller.orientation = controller.orientation.from_axis_angle(
        Vec3.axis(0),
        math.pi * 0.5,
    )

    restored = controller.restore_state(original)

    assert restored == original
    assert controller.capture_state() == original
    assert controller.position == Vec3(0.0, 1.0, 0.0)
    assert controller.up == Vec3.axis(1)
    assert controller.settings.half_height == pytest.approx(0.6)


def test_restore_recomputes_orientation_from_restored_up_axis() -> None:
    source = _controller(
        up=Vec3.axis(2),
        position=Vec3(1.0, 2.0, 3.0),
    )
    state = source.capture_state()
    target = _controller()

    target.restore_state(state)

    assert target.up == Vec3.axis(2)
    rotated_local_up = target.orientation.rotate(Vec3.axis(1))
    assert rotated_local_up.almost_equal(Vec3.axis(2), tolerance=1.0e-9)


def test_tampered_position_is_rejected_by_digest() -> None:
    state = _controller().capture_state()
    tampered = replace(
        state,
        position=state.position + Vec3(1.0, 0.0, 0.0),
    )

    with pytest.raises(PhysicsSnapshotError, match="digest mismatch"):
        verify_character_state(tampered)


def test_tampered_settings_are_rejected_by_digest() -> None:
    state = _controller().capture_state()
    tampered = replace(
        state,
        settings=replace(state.settings, step_height=0.5),
    )

    with pytest.raises(PhysicsSnapshotError, match="digest mismatch"):
        verify_character_state(tampered)


def test_tampered_up_axis_is_rejected_by_digest() -> None:
    state = _controller().capture_state()
    tampered = replace(
        state,
        up=Vec3.axis(2),
    )

    with pytest.raises(PhysicsSnapshotError, match="digest mismatch"):
        verify_character_state(tampered)


def test_invalid_digest_encoding_fails_at_state_construction() -> None:
    state = _controller().capture_state()

    with pytest.raises(PhysicsSnapshotError, match="hexadecimal"):
        replace(state, state_digest="z" * 64)


def test_boolean_snapshot_version_does_not_alias_integer_version() -> None:
    state = _controller().capture_state()

    with pytest.raises(PhysicsSnapshotError, match="version"):
        replace(state, version=True)


def test_non_normalized_snapshot_up_fails_closed_before_restore() -> None:
    state = _controller().capture_state()

    with pytest.raises(PhysicsSnapshotError, match="normalized"):
        replace(state, up=Vec3(0.0, 2.0, 0.0))


def test_restore_rejects_valid_state_from_different_character_identity() -> None:
    target = _controller("target")
    foreign = _controller("foreign").capture_state()
    before = target.capture_state()

    with pytest.raises(PhysicsSnapshotError, match="identity"):
        target.restore_state(foreign)

    assert target.capture_state() == before


def test_failed_restore_is_atomic() -> None:
    controller = _controller()
    before = controller.capture_state()
    tampered = replace(
        before,
        position=Vec3(50.0, 0.0, 0.0),
    )

    with pytest.raises(PhysicsSnapshotError, match="digest"):
        controller.restore_state(tampered)

    assert controller.capture_state() == before


def test_verify_character_state_rejects_wrong_public_type() -> None:
    with pytest.raises(PhysicsValidationError, match="CharacterControllerState"):
        verify_character_state(object())  # type: ignore[arg-type]


def test_build_character_state_rejects_wrong_settings_type() -> None:
    with pytest.raises(PhysicsValidationError, match="settings"):
        build_character_state(
            body_id="character",
            position=Vec3.zero(),
            up=Vec3.axis(1),
            settings=object(),  # type: ignore[arg-type]
        )


def test_runtime_rerun_is_identical_after_state_restore() -> None:
    controller = _controller(position=Vec3(0.0, 1.12, 0.0))
    platform = RigidBody.kinematic(
        "platform",
        BoxShape(Vec3(2.0, 0.1, 2.0)),
        linear_velocity=Vec3(1.0, 0.0, 0.0),
    )
    state = controller.capture_state()

    first = controller.runtime_step(
        Vec3(0.0, 0.0, 2.0),
        (platform,),
        dt=0.25,
    )
    first_final = controller.capture_state()

    controller.restore_state(state)
    second = controller.runtime_step(
        Vec3(0.0, 0.0, 2.0),
        (platform,),
        dt=0.25,
    )

    assert second == first
    assert controller.capture_state() == first_final


def test_recovery_then_restore_recovers_exact_pre_recovery_state() -> None:
    controller = _controller()
    wall = RigidBody.static(
        "wall",
        BoxShape(Vec3(0.25, 2.0, 2.0)),
        position=Vec3(0.5, 1.0, 0.0),
    )
    before = controller.capture_state()

    recovery = controller.recover_overlaps((wall,))
    assert recovery.recovered
    assert controller.capture_state() != before

    controller.restore_state(before)

    assert controller.capture_state() == before


def test_resize_then_restore_recovers_exact_capsule_geometry() -> None:
    controller = _controller()
    before = controller.capture_state()

    result = controller.resize(0.3, ())
    assert result.changed
    assert controller.shape.half_height == pytest.approx(0.3)

    controller.restore_state(before)

    assert controller.shape.half_height == pytest.approx(0.6)
    assert controller.capture_state() == before


def test_character_controller_state_constructor_requires_supported_version() -> None:
    state = _controller().capture_state()

    with pytest.raises(PhysicsSnapshotError, match="version"):
        CharacterControllerState(
            version=2,
            body_id=state.body_id,
            position=state.position,
            up=state.up,
            settings=state.settings,
            state_digest=state.state_digest,
        )
