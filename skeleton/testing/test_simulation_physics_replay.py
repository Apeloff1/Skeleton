"""Rollback and replay contracts for deterministic physics."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.simulation.physics import (
    PhysicsReplayDivergenceError,
    PhysicsReplayError,
    PhysicsReplayRecorder,
    PhysicsRollbackSession,
    PhysicsReplayTape,
    PhysicsSettings,
    PhysicsSnapshotError,
    PhysicsWorld,
    PlaneShape,
    RigidBody,
    SphereShape,
    Vec3,
    build_snapshot,
    replay_physics,
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

    bad_frame = replace(tape.frames[1], after_digest="f" * 64)
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
