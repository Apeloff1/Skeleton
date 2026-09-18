"""Character input rollback, correction, and resimulation regressions."""
from __future__ import annotations

import pytest

from skeleton.simulation.physics import (
    CharacterInputFrame,
    CharacterRollbackSession,
    KinematicCapsuleController,
    PhysicsReplayError,
    PhysicsSnapshotError,
    PhysicsValidationError,
    RigidBody,
    Vec3,
)


def _controller() -> KinematicCapsuleController:
    return KinematicCapsuleController(
        "character",
        position=Vec3.zero(),
    )


def _empty_bodies(_tick: int) -> tuple[RigidBody, ...]:
    return ()


def test_character_input_frame_canonicalizes_ignore_and_digest() -> None:
    first = CharacterInputFrame(
        tick=1,
        requested_velocity=Vec3(1.0, 2.0, 3.0),
        dt=0.1,
        ignore=("z", "a", "z"),
    )
    second = CharacterInputFrame(
        tick=1,
        requested_velocity=Vec3(1.0, 2.0, 3.0),
        dt=0.1,
        ignore=("a", "z"),
    )

    assert first.ignore == ("a", "z")
    assert first == second
    assert first.frame_digest == second.frame_digest


@pytest.mark.parametrize(
    "kwargs",
    (
        {"tick": 0},
        {"tick": True},
        {"dt": 0.0},
        {"dt": float("inf")},
        {"requested_velocity": object()},
        {"ignore": ("",)},
        {"recover_overlaps": 1},
        {"carry_support": 0},
    ),
)
def test_character_input_frame_rejects_invalid_contract(kwargs) -> None:
    values = {
        "tick": 1,
        "requested_velocity": Vec3.zero(),
        "dt": 0.1,
    }
    values.update(kwargs)

    with pytest.raises(PhysicsValidationError):
        CharacterInputFrame(**values)  # type: ignore[arg-type]


def test_character_rollback_session_validates_capacity() -> None:
    controller = _controller()

    with pytest.raises(PhysicsSnapshotError, match="history_capacity"):
        CharacterRollbackSession(controller, history_capacity=1)
    with pytest.raises(PhysicsSnapshotError, match="command_capacity"):
        CharacterRollbackSession(controller, command_capacity=1)


def test_character_session_step_records_state_input_and_receipt() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=8)

    receipt = session.step(
        Vec3(2.0, 0.0, 0.0),
        (),
        dt=0.25,
    )

    assert receipt.tick == 1
    assert session.tick == 1
    assert controller.position.x == pytest.approx(0.5)
    assert receipt.after_digest == controller.state_digest
    assert receipt.before_digest != receipt.after_digest
    assert receipt.frame_digest == session.input_at(1).frame_digest
    assert session.state_at(1).state_digest == controller.state_digest
    assert session.state_ticks() == (0, 1)
    assert session.input_ticks() == (1,)


def test_rollback_restores_exact_controller_state_but_retains_inputs() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=8)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    state_one = controller.capture_state()
    session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)

    receipt = session.rollback_to(1)

    assert receipt.from_tick == 2
    assert receipt.to_tick == 1
    assert receipt.discarded_states == 1
    assert controller.capture_state() == state_one
    assert session.state_ticks() == (0, 1)
    assert session.input_ticks() == (1, 2)


def test_identical_retained_future_input_can_be_replayed_after_rollback() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=8)
    first = session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    second = session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    final = controller.capture_state()

    session.rollback_to(1)
    replayed = session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)

    assert first.tick == 1
    assert replayed.tick == second.tick
    assert replayed.frame_digest == second.frame_digest
    assert controller.capture_state() == final


def test_conflicting_retained_future_input_fails_before_mutation() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=8)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    session.rollback_to(1)
    before = controller.capture_state()

    with pytest.raises(PhysicsReplayError, match="different retained input"):
        session.step(Vec3(3.0, 0.0, 0.0), (), dt=0.1)

    assert session.tick == 1
    assert controller.capture_state() == before
    assert session.input_at(2).requested_velocity == Vec3(2.0, 0.0, 0.0)


def test_resimulate_to_replays_retained_inputs_exactly() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=8)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(-0.5, 0.0, 0.0), (), dt=0.2)
    final = controller.capture_state()

    session.rollback_to(0)
    receipts = session.resimulate_to(3, _empty_bodies)

    assert tuple(receipt.tick for receipt in receipts) == (1, 2, 3)
    assert controller.capture_state() == final
    assert session.tick == 3


def test_late_input_correction_matches_fresh_corrected_simulation() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=16)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    before_digest = controller.state_digest

    corrected = CharacterInputFrame(
        tick=2,
        requested_velocity=Vec3(2.0, 0.0, 0.0),
        dt=0.1,
    )
    receipt = session.correct_and_resimulate(
        corrected,
        bodies_at_tick=_empty_bodies,
    )

    fresh = _controller()
    fresh.runtime_step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    fresh.runtime_step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    fresh.runtime_step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)

    assert receipt.corrected_tick == 2
    assert receipt.rollback_tick == 1
    assert receipt.resimulated_through_tick == 3
    assert receipt.before_digest == before_digest
    assert receipt.after_digest == fresh.state_digest
    assert controller.capture_state() == fresh.capture_state()
    assert session.input_at(2) == corrected


def test_correction_failure_restores_state_tick_inputs_and_history_exactly() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=16)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(3.0, 0.0, 0.0), (), dt=0.1)

    before_state = controller.capture_state()
    before_tick = session.tick
    before_history = session.history_digest
    before_commands = session.command_digest
    original_frame = session.input_at(2)

    corrected = CharacterInputFrame(
        tick=2,
        requested_velocity=Vec3(20.0, 0.0, 0.0),
        dt=0.1,
    )

    def fail_at_three(tick: int) -> tuple[RigidBody, ...]:
        if tick == 3:
            raise RuntimeError("synthetic body-provider failure")
        return ()

    with pytest.raises(RuntimeError, match="body-provider"):
        session.correct_and_resimulate(
            corrected,
            bodies_at_tick=fail_at_three,
        )

    assert session.tick == before_tick
    assert controller.capture_state() == before_state
    assert session.history_digest == before_history
    assert session.command_digest == before_commands
    assert session.input_at(2) == original_frame


def test_history_capacity_eviction_blocks_correction_without_preceding_state() -> None:
    controller = _controller()
    session = CharacterRollbackSession(
        controller,
        history_capacity=2,
        command_capacity=8,
    )
    for _ in range(3):
        session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)

    assert session.state_ticks() == (2, 3)
    corrected = CharacterInputFrame(
        tick=2,
        requested_velocity=Vec3(2.0, 0.0, 0.0),
        dt=0.1,
    )

    with pytest.raises(PhysicsSnapshotError, match="preceding"):
        session.correct_and_resimulate(
            corrected,
            bodies_at_tick=_empty_bodies,
        )


def test_command_capacity_eviction_is_deterministic() -> None:
    controller = _controller()
    session = CharacterRollbackSession(
        controller,
        history_capacity=8,
        command_capacity=2,
    )
    for _ in range(3):
        session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)

    assert session.input_ticks() == (2, 3)
    with pytest.raises(PhysicsReplayError, match="not retained"):
        session.input_at(1)


def test_rollback_to_evicted_state_fails_without_mutation() -> None:
    controller = _controller()
    session = CharacterRollbackSession(
        controller,
        history_capacity=2,
        command_capacity=8,
    )
    for _ in range(3):
        session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    before = controller.capture_state()

    with pytest.raises(PhysicsSnapshotError, match="not retained"):
        session.rollback_to(1)

    assert session.tick == 3
    assert controller.capture_state() == before


def test_resimulation_fails_when_required_command_was_evicted() -> None:
    controller = _controller()
    session = CharacterRollbackSession(
        controller,
        history_capacity=8,
        command_capacity=2,
    )
    for _ in range(4):
        session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)

    session.rollback_to(1)
    with pytest.raises(PhysicsReplayError, match="not retained"):
        session.resimulate_to(2, _empty_bodies)


def test_step_failure_rolls_back_command_and_character_state() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=8)
    before = controller.capture_state()
    before_history = session.history_digest

    with pytest.raises(PhysicsValidationError, match="bodies"):
        session.step(
            Vec3(1.0, 0.0, 0.0),
            object(),  # type: ignore[arg-type]
            dt=0.1,
        )

    assert session.tick == 0
    assert controller.capture_state() == before
    assert session.input_ticks() == ()
    assert session.state_ticks() == (0,)
    assert session.history_digest == before_history


def test_resimulation_requires_callable_body_provider() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.rollback_to(0)

    with pytest.raises(PhysicsValidationError, match="callable"):
        session.resimulate_to(1, object())  # type: ignore[arg-type]


def test_identical_sessions_produce_identical_history_and_command_digests() -> None:
    left = CharacterRollbackSession(_controller(), history_capacity=8)
    right = CharacterRollbackSession(_controller(), history_capacity=8)

    inputs = (
        Vec3(1.0, 0.0, 0.0),
        Vec3(0.0, 0.0, 2.0),
        Vec3(-0.5, 0.0, 0.25),
    )
    for velocity in inputs:
        left.step(velocity, (), dt=0.1)
        right.step(velocity, (), dt=0.1)

    assert left.command_digest == right.command_digest
    assert left.history_digest == right.history_digest
    assert left.controller.capture_state() == right.controller.capture_state()


def test_history_digest_changes_when_retained_input_changes_after_correction() -> None:
    session = CharacterRollbackSession(_controller(), history_capacity=8)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    before = session.history_digest

    session.correct_and_resimulate(
        CharacterInputFrame(
            tick=2,
            requested_velocity=Vec3(2.0, 0.0, 0.0),
            dt=0.1,
        ),
        bodies_at_tick=_empty_bodies,
    )

    assert session.history_digest != before


def test_state_and_input_lookup_validate_retention() -> None:
    session = CharacterRollbackSession(_controller())

    with pytest.raises(PhysicsSnapshotError, match="not retained"):
        session.state_at(10)
    with pytest.raises(PhysicsReplayError, match="not retained"):
        session.input_at(10)


def test_correction_rejects_unretained_frame() -> None:
    session = CharacterRollbackSession(_controller())
    frame = CharacterInputFrame(
        tick=1,
        requested_velocity=Vec3.zero(),
        dt=0.1,
    )

    with pytest.raises(PhysicsReplayError, match="not retained"):
        session.correct_and_resimulate(
            frame,
            bodies_at_tick=_empty_bodies,
        )


def test_correction_rejects_invalid_through_tick() -> None:
    session = CharacterRollbackSession(_controller())
    session.step(Vec3.zero(), (), dt=0.1)
    frame = CharacterInputFrame(
        tick=1,
        requested_velocity=Vec3(1.0, 0.0, 0.0),
        dt=0.1,
    )

    with pytest.raises(PhysicsReplayError, match="through_tick"):
        session.correct_and_resimulate(
            frame,
            bodies_at_tick=_empty_bodies,
            through_tick=0,
        )



def test_failed_step_at_full_command_capacity_restores_evicted_frame() -> None:
    controller = _controller()
    session = CharacterRollbackSession(
        controller,
        history_capacity=8,
        command_capacity=2,
    )
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    session.rollback_to(1)
    before_state = controller.capture_state()
    before_inputs = session.input_ticks()
    before_command_digest = session.command_digest

    # Tick 2 already exists, so move to tick 2 identically first, then the
    # failing tick 3 append would evict tick 1 if not rolled back atomically.
    session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    before_failure = controller.capture_state()
    before_failure_inputs = session.input_ticks()
    before_failure_digest = session.command_digest

    with pytest.raises(PhysicsValidationError, match="bodies"):
        session.step(
            Vec3(3.0, 0.0, 0.0),
            object(),  # type: ignore[arg-type]
            dt=0.1,
        )

    assert controller.capture_state() == before_failure
    assert session.tick == 2
    assert session.input_ticks() == before_failure_inputs
    assert session.command_digest == before_failure_digest
    assert session.input_at(1).requested_velocity == Vec3(1.0, 0.0, 0.0)
    assert before_inputs == (1, 2)
    assert before_command_digest != ""
    assert before_state != before_failure


def test_direct_resimulation_failure_is_atomic() -> None:
    controller = _controller()
    session = CharacterRollbackSession(controller, history_capacity=8)
    session.step(Vec3(1.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(2.0, 0.0, 0.0), (), dt=0.1)
    session.step(Vec3(3.0, 0.0, 0.0), (), dt=0.1)
    session.rollback_to(0)

    before_state = controller.capture_state()
    before_tick = session.tick
    before_history = session.history_digest
    before_states = session.state_ticks()

    def fail_after_one_tick(tick: int) -> tuple[RigidBody, ...]:
        if tick == 2:
            raise RuntimeError("synthetic resimulation failure")
        return ()

    with pytest.raises(RuntimeError, match="resimulation"):
        session.resimulate_to(3, fail_after_one_tick)

    assert controller.capture_state() == before_state
    assert session.tick == before_tick
    assert session.state_ticks() == before_states
    assert session.history_digest == before_history
