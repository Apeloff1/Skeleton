"""Rollback and replay contracts for deterministic physics."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.simulation.physics import (
    PhysicsCommand,
    PhysicsCommandFrame,
    PhysicsCommandKind,
    PhysicsCommandReplayRecorder,
    PhysicsCommandRollbackSession,
    PhysicsCommandReplayTape,
    PhysicsReplayDivergenceError,
    PhysicsReplayError,
    PhysicsReplayRecorder,
    PhysicsRollbackSession,
    PhysicsReplayTape,
    PhysicsSettings,
    PhysicsSnapshotError,
    PhysicsValidationError,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    SphereShape,
    Vec3,
    build_snapshot,
    replay_physics,
    replay_physics_commands,
    step_physics_with_commands,
)


def _world() -> PhysicsWorld:
    world = PhysicsWorld(
        PhysicsSettings(
            fixed_dt=1.0 / 120.0,
            gravity=Vec3(0.0, -9.81, 0.0),
            sleep_after_seconds=10.0,
            velocity_iterations=8,
            position_iterations=4,
        )
    )
    world.add_body(RigidBody.static("ground", PlaneShape()))
    ball = RigidBody.dynamic(
        "ball",
        SphereShape(0.5),
        position=Vec3(0.0, 1.0, 0.0),
        linear_damping=0.0,
        angular_damping=0.0,
    )
    ball.linear_velocity = Vec3(0.25, 0.0, 0.1)
    world.add_body(ball)
    return world


def test_snapshot_round_trip_restores_exact_authoritative_state() -> None:
    world = _world()
    world.step(50)
    snapshot = world.capture_snapshot()
    captured_contacts = world.contacts()
    captured_tick = world.tick
    captured_digest = world.state_digest
    captured_position = world.get_body("ball").position

    world.get_body("ball").apply_impulse(Vec3(10.0, 5.0, -3.0))
    world.step(10)
    assert world.state_digest != captured_digest

    world.restore_snapshot(snapshot)
    assert world.tick == captured_tick
    assert world.state_digest == captured_digest
    assert world.get_body("ball").position == captured_position
    assert world.contacts() == captured_contacts


def test_snapshot_restore_rejects_configuration_mismatch() -> None:
    source = _world()
    source.step(3)
    snapshot = source.capture_snapshot()

    incompatible = PhysicsWorld(source.settings)
    incompatible.add_body(RigidBody.static("ground", PlaneShape()))
    incompatible.add_body(
        RigidBody.dynamic(
            "ball",
            SphereShape(0.75),
            position=Vec3(0.0, 1.0, 0.0),
            linear_damping=0.0,
            angular_damping=0.0,
        )
    )
    before = incompatible.state_digest
    with pytest.raises(PhysicsSnapshotError, match="configuration"):
        incompatible.restore_snapshot(snapshot)
    assert incompatible.state_digest == before


def test_snapshot_digest_tamper_is_rejected_before_mutation() -> None:
    world = _world()
    world.step(2)
    snapshot = world.capture_snapshot()
    bad = replace(snapshot, snapshot_digest="f" * 64)
    before = world.state_digest
    before_tick = world.tick

    with pytest.raises(PhysicsSnapshotError, match="digest"):
        world.restore_snapshot(bad)

    assert world.state_digest == before
    assert world.tick == before_tick


def test_self_consistent_envelope_with_false_state_digest_rolls_back_restore() -> None:
    world = _world()
    world.step(5)
    snapshot = world.capture_snapshot()

    altered_states = tuple(
        replace(state, position=state.position + Vec3(100.0, 0.0, 0.0))
        if state.body_id == "ball"
        else state
        for state in snapshot.body_states
    )
    malicious = build_snapshot(
        tick=snapshot.tick,
        configuration_digest=snapshot.configuration_digest,
        body_states=altered_states,
        contact_cache=snapshot.contact_cache,
        manifolds=snapshot.manifolds,
        state_digest=snapshot.state_digest,
    )

    before_digest = world.state_digest
    before_position = world.get_body("ball").position
    before_tick = world.tick

    with pytest.raises(PhysicsSnapshotError, match="state digest"):
        world.restore_snapshot(malicious)

    assert world.state_digest == before_digest
    assert world.get_body("ball").position == before_position
    assert world.tick == before_tick


def test_snapshot_binds_force_accumulators() -> None:
    world = _world()
    body = world.get_body("ball")
    body.apply_force(Vec3(3.0, 4.0, 5.0))
    snapshot = world.capture_snapshot()
    body.clear_accumulators()
    assert world.state_digest != snapshot.state_digest
    world.restore_snapshot(snapshot)
    assert body.force == Vec3(3.0, 4.0, 5.0)
    assert world.state_digest == snapshot.state_digest


def test_replay_reconstructs_exact_contact_and_warm_start_run() -> None:
    world = _world()
    recorder = PhysicsReplayRecorder(world)
    for _ in range(60):
        recorder.step()
    tape = recorder.tape()

    verification = replay_physics(_world, tape)
    assert verification.ok
    assert verification.frames == 60
    assert verification.final_digest == world.state_digest
    assert verification.chain_digest == tape.chain_digest


def test_replay_detects_tampered_frame_state_digest() -> None:
    recorder = PhysicsReplayRecorder(_world())
    for _ in range(4):
        recorder.step()
    tape = recorder.tape()

    bad_frame = replace(tape.frames[1], receipt_digest="f" * 64)
    tampered = replace(
        tape,
        frames=(tape.frames[0], bad_frame, *tape.frames[2:]),
    )

    with pytest.raises(PhysicsReplayDivergenceError, match="frame 1"):
        replay_physics(_world, tampered)


def test_replay_detects_tampered_chain_digest() -> None:
    recorder = PhysicsReplayRecorder(_world())
    recorder.step()
    recorder.step()
    tape = replace(recorder.tape(), chain_digest="f" * 64)

    with pytest.raises(PhysicsReplayDivergenceError, match="chain"):
        replay_physics(_world, tape)


def test_replay_tape_rejects_noncontiguous_frame_index() -> None:
    recorder = PhysicsReplayRecorder(_world())
    recorder.step()
    tape = recorder.tape()
    bad_frame = replace(tape.frames[0], index=4)

    with pytest.raises(PhysicsReplayError, match="indices"):
        PhysicsReplayTape(
            initial=tape.initial,
            frames=(bad_frame,),
            chain_digest=tape.chain_digest,
        )


def test_replay_tape_rejects_noncontiguous_tick() -> None:
    recorder = PhysicsReplayRecorder(_world())
    recorder.step()
    tape = recorder.tape()
    bad_frame = replace(tape.frames[0], tick=tape.frames[0].tick + 5)

    with pytest.raises(PhysicsReplayError, match="ticks"):
        PhysicsReplayTape(
            initial=tape.initial,
            frames=(bad_frame,),
            chain_digest=tape.chain_digest,
        )


def test_replay_detects_changed_runtime_logic_via_configuration_guard() -> None:
    recorder = PhysicsReplayRecorder(_world())
    recorder.step()
    tape = recorder.tape()

    def changed_world() -> PhysicsWorld:
        world = PhysicsWorld(
            PhysicsSettings(
                fixed_dt=1.0 / 60.0,
                gravity=Vec3(0.0, -9.81, 0.0),
                sleep_after_seconds=10.0,
            )
        )
        world.add_body(RigidBody.static("ground", PlaneShape()))
        world.add_body(
            RigidBody.dynamic(
                "ball",
                SphereShape(0.5),
                position=Vec3(0.0, 1.0, 0.0),
                linear_damping=0.0,
                angular_damping=0.0,
            )
        )
        return world

    with pytest.raises(PhysicsSnapshotError, match="configuration"):
        replay_physics(changed_world, tape)



def test_zero_frame_replay_chain_still_binds_initial_snapshot() -> None:
    recorder = PhysicsReplayRecorder(_world())
    tape = recorder.tape()
    assert tape.chain_digest != "0" * 64

    alternate = _world()
    alternate.get_body("ball").apply_impulse(Vec3(1.0, 0.0, 0.0))
    alternate_initial = alternate.capture_snapshot()
    tampered = replace(tape, initial=alternate_initial)

    with pytest.raises(PhysicsReplayDivergenceError, match="chain"):
        replay_physics(_world, tampered)



def test_replay_tape_rejects_broken_state_digest_chain() -> None:
    recorder = PhysicsReplayRecorder(_world())
    recorder.step()
    recorder.step()
    tape = recorder.tape()
    bad_second = replace(tape.frames[1], before_digest="f" * 64)
    with pytest.raises(PhysicsReplayError, match="state chain"):
        PhysicsReplayTape(
            initial=tape.initial,
            frames=(tape.frames[0], bad_second),
            chain_digest=tape.chain_digest,
        )



def test_rollback_session_restores_and_resimulates_exact_state() -> None:
    world = _world()
    session = PhysicsRollbackSession(world, capacity=128)
    session.step(40)
    final_digest = world.state_digest
    final_position = world.get_body("ball").position
    assert session.snapshot_at(40).state_digest == final_digest

    receipt = session.rollback_to(15)
    assert receipt.from_tick == 40
    assert receipt.to_tick == 15
    assert world.tick == 15
    assert session.history.ticks()[-1] == 15

    session.resimulate_to(40)
    assert world.tick == 40
    assert world.state_digest == final_digest
    assert world.get_body("ball").position == final_position


def test_rollback_session_history_is_bounded() -> None:
    session = PhysicsRollbackSession(_world(), capacity=4)
    session.step(8)
    assert len(session.history) == 4
    assert session.history.ticks() == (5, 6, 7, 8)


def test_rollback_session_rejects_world_topology_change() -> None:
    world = _world()
    session = PhysicsRollbackSession(world)
    world.add_body(
        RigidBody.dynamic(
            "extra",
            SphereShape(0.25),
            position=Vec3(4.0, 4.0, 0.0),
        )
    )
    with pytest.raises(PhysicsSnapshotError, match="configuration changed"):
        session.step()


def test_rollback_history_digest_changes_with_retained_timeline() -> None:
    session = PhysicsRollbackSession(_world())
    initial_digest = session.history_digest
    session.step(2)
    later_digest = session.history_digest
    assert later_digest != initial_digest
    session.rollback_to(0)
    assert session.history_digest == initial_digest


def test_rollback_session_rejects_invalid_step_count() -> None:
    session = PhysicsRollbackSession(_world())
    with pytest.raises(PhysicsSnapshotError, match="steps"):
        session.step(0)



def test_command_frame_rejects_noncontiguous_sequence() -> None:
    commands = (
        PhysicsCommand(
            1,
            "ball",
            PhysicsCommandKind.APPLY_IMPULSE,
            Vec3(1.0, 0.0, 0.0),
        ),
    )
    with pytest.raises(PhysicsReplayError, match="contiguous"):
        PhysicsCommandFrame.build(1, commands)


def test_command_frame_digest_detects_payload_tamper() -> None:
    frame = PhysicsCommandFrame.build(
        1,
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_FORCE,
                Vec3(1.0, 2.0, 3.0),
            ),
        ),
    )
    altered_command = replace(frame.commands[0], vector=Vec3(9.0, 2.0, 3.0))
    with pytest.raises(PhysicsReplayError, match="digest mismatch"):
        replace(frame, commands=(altered_command,))


def test_invalid_late_command_rolls_back_earlier_command_atomically() -> None:
    world = _world()
    body = world.get_body("ball")
    before_digest = world.state_digest
    before_velocity = body.linear_velocity
    frame = PhysicsCommandFrame.build(
        1,
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_IMPULSE,
                Vec3(10.0, 0.0, 0.0),
            ),
            PhysicsCommand(
                1,
                "ground",
                PhysicsCommandKind.APPLY_FORCE,
                Vec3(100.0, 0.0, 0.0),
            ),
        ),
    )

    with pytest.raises(PhysicsValidationError, match="dynamic body"):
        step_physics_with_commands(world, frame)

    assert world.tick == 0
    assert world.state_digest == before_digest
    assert body.linear_velocity == before_velocity


def test_command_replay_reconstructs_input_driven_run_exactly() -> None:
    world = _world()
    recorder = PhysicsCommandReplayRecorder(world)

    recorder.step(
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_IMPULSE,
                Vec3(2.0, 3.0, 0.0),
            ),
        )
    )
    recorder.step(
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_FORCE,
                Vec3(0.0, 12.0, 4.0),
            ),
            PhysicsCommand(
                1,
                "ball",
                PhysicsCommandKind.APPLY_TORQUE,
                Vec3(0.0, 1.0, 0.0),
            ),
        )
    )
    recorder.step(
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.SET_LINEAR_VELOCITY,
                Vec3(-1.0, 2.0, 0.5),
            ),
        )
    )
    for _ in range(20):
        recorder.step()

    tape = recorder.tape()
    verification = replay_physics_commands(_world, tape)
    assert verification.ok
    assert verification.frames == len(tape.frames)
    assert verification.final_digest == world.state_digest
    assert verification.chain_digest == tape.chain_digest


def test_command_replay_records_pre_and_post_command_state() -> None:
    world = _world()
    recorder = PhysicsCommandReplayRecorder(world)
    initial = world.state_digest
    recorder.step(
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_IMPULSE,
                Vec3(3.0, 0.0, 0.0),
            ),
        )
    )
    frame = recorder.tape().frames[0]
    assert frame.before_digest == initial
    assert frame.simulation_before_digest != initial
    assert frame.after_digest == world.state_digest


def test_command_replay_detects_valid_but_altered_input_frame() -> None:
    recorder = PhysicsCommandReplayRecorder(_world())
    recorder.step(
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_IMPULSE,
                Vec3(1.0, 0.0, 0.0),
            ),
        )
    )
    tape = recorder.tape()
    altered_commands = PhysicsCommandFrame.build(
        1,
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_IMPULSE,
                Vec3(5.0, 0.0, 0.0),
            ),
        ),
    )
    altered_frame = replace(tape.frames[0], commands=altered_commands)
    altered_tape = PhysicsCommandReplayTape(
        initial=tape.initial,
        frames=(altered_frame,),
        chain_digest=tape.chain_digest,
    )
    with pytest.raises(PhysicsReplayDivergenceError, match="frame 0"):
        replay_physics_commands(_world, altered_tape)


def test_command_step_requires_next_tick_frame() -> None:
    world = _world()
    frame = PhysicsCommandFrame.build(2, ())
    with pytest.raises(PhysicsValidationError, match="next simulation tick"):
        step_physics_with_commands(world, frame)



def _impulse_command(sequence: int, value: float) -> PhysicsCommand:
    return PhysicsCommand(
        sequence,
        "ball",
        PhysicsCommandKind.APPLY_IMPULSE,
        Vec3(value, 0.0, 0.0),
    )


def test_late_command_correction_matches_fresh_corrected_simulation() -> None:
    world = _world()
    session = PhysicsCommandRollbackSession(world, history_capacity=64)
    session.step((_impulse_command(0, 1.0),))
    session.step(())
    session.step(
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_FORCE,
                Vec3(0.0, 8.0, 0.0),
            ),
        )
    )
    session.step(())
    original_digest = world.state_digest

    correction = session.correct_and_resimulate(
        1,
        (_impulse_command(0, 3.0),),
    )
    corrected_digest = world.state_digest
    assert correction.corrected_tick == 1
    assert correction.resimulated_through_tick == 4
    assert corrected_digest != original_digest

    fresh = _world()
    fresh_session = PhysicsCommandRollbackSession(fresh, history_capacity=64)
    fresh_session.step((_impulse_command(0, 3.0),))
    fresh_session.step(())
    fresh_session.step(
        (
            PhysicsCommand(
                0,
                "ball",
                PhysicsCommandKind.APPLY_FORCE,
                Vec3(0.0, 8.0, 0.0),
            ),
        )
    )
    fresh_session.step(())

    assert fresh.tick == world.tick == 4
    assert fresh.state_digest == corrected_digest
    assert fresh_session.commands.tape_digest == session.commands.tape_digest


def test_failed_late_input_correction_restores_world_commands_and_history() -> None:
    world = _world()
    session = PhysicsCommandRollbackSession(world, history_capacity=64)
    session.step((_impulse_command(0, 1.0),))
    session.step(())
    session.step((_impulse_command(0, 0.5),))

    before_digest = world.state_digest
    before_tick = world.tick
    before_history_digest = session.history_digest
    before_tape_digest = session.commands.tape_digest
    before_ticks = session.history.ticks()
    original_frame = session.commands.frame(1)

    class _FailingConstraintSolver:
        def solve(self, bodies, joints, *, dt):
            raise RuntimeError("synthetic correction failure")

    world._constraint_solver = _FailingConstraintSolver()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="synthetic correction failure"):
        session.correct_and_resimulate(
            1,
            (_impulse_command(0, 9.0),),
        )

    assert world.tick == before_tick
    assert world.state_digest == before_digest
    assert session.history.ticks() == before_ticks
    assert session.history_digest == before_history_digest
    assert session.commands.tape_digest == before_tape_digest
    assert session.commands.frame(1) == original_frame


def test_command_rollback_requires_preceding_snapshot_to_correct() -> None:
    session = PhysicsCommandRollbackSession(_world(), history_capacity=2)
    for _ in range(5):
        session.step(())
    before = session.world.state_digest
    with pytest.raises(PhysicsSnapshotError, match="not retained"):
        session.correct_and_resimulate(
            1,
            (_impulse_command(0, 2.0),),
        )
    assert session.world.state_digest == before


def test_command_tape_correction_changes_evidence_digest() -> None:
    session = PhysicsCommandRollbackSession(_world())
    session.step((_impulse_command(0, 1.0),))
    before = session.commands.tape_digest
    session.commands.replace(
        PhysicsCommandFrame.build(
            1,
            (_impulse_command(0, 2.0),),
        )
    )
    assert session.commands.tape_digest != before



def test_rewind_step_rejects_conflicting_retained_commands_without_erasing_future() -> None:
    session = PhysicsCommandRollbackSession(_world(), history_capacity=32)
    session.step((_impulse_command(0, 1.0),))
    session.step((_impulse_command(0, 2.0),))
    session.step((_impulse_command(0, 3.0),))
    tape_before = session.commands.tape_digest
    retained_ticks = session.commands.ticks()

    session.rollback_to(1)
    state_before = session.world.state_digest
    with pytest.raises(PhysicsReplayError, match="use correction"):
        session.step((_impulse_command(0, 99.0),))

    assert session.world.tick == 1
    assert session.world.state_digest == state_before
    assert session.commands.ticks() == retained_ticks
    assert session.commands.tape_digest == tape_before


def test_rewind_step_can_reuse_identical_retained_command_frame() -> None:
    session = PhysicsCommandRollbackSession(_world(), history_capacity=32)
    session.step((_impulse_command(0, 1.0),))
    session.step((_impulse_command(0, 2.0),))
    final_digest = session.world.state_digest

    session.rollback_to(1)
    session.step((_impulse_command(0, 2.0),))
    assert session.world.tick == 2
    assert session.world.state_digest == final_digest



def test_public_snapshot_builder_rejects_non_iterable_collections() -> None:
    snapshot = _world().capture_snapshot()
    with pytest.raises(PhysicsSnapshotError, match="iterable"):
        build_snapshot(
            tick=snapshot.tick,
            configuration_digest=snapshot.configuration_digest,
            body_states=None,  # type: ignore[arg-type]
            contact_cache=snapshot.contact_cache,
            manifolds=snapshot.manifolds,
            state_digest=snapshot.state_digest,
        )


def test_public_snapshot_builder_rejects_wrong_collection_types() -> None:
    snapshot = _world().capture_snapshot()
    with pytest.raises(PhysicsSnapshotError, match="invalid body state"):
        build_snapshot(
            tick=snapshot.tick,
            configuration_digest=snapshot.configuration_digest,
            body_states=(object(),),  # type: ignore[arg-type]
            contact_cache=snapshot.contact_cache,
            manifolds=snapshot.manifolds,
            state_digest=snapshot.state_digest,
        )
