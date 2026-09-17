"""Rollback and replay contracts for deterministic physics."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.simulation.physics import (
    PhysicsReplayDivergenceError,
    PhysicsReplayError,
    PhysicsReplayRecorder,
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
