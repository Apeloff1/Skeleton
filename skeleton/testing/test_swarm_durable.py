"""Adversarial integration tests for durable swarm recovery."""

from __future__ import annotations

import pytest

from skeleton.agents.swarm_durable import DurableSwarmError, SwarmDurableBridge
from skeleton.agents.swarm_recovery import RECOVERY_ARCHIVE_VERSION, SwarmRecoveryManager
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState
from skeleton.state import PayloadTooLarge, SQLiteRunStore, StateConflict, StepStatus


def make_bridge(tmp_path, **store_kwargs):
    store = SQLiteRunStore(tmp_path / "runs.sqlite3", **store_kwargs)
    store.create_run("run-1", {"kind": "swarm"})
    store.claim_run("run-1", "outer-worker", lease_seconds=300)
    return store, SwarmDurableBridge(store)


def test_capture_persists_and_restores_canonical_swarm_archive(tmp_path):
    store, bridge = make_bridge(tmp_path)
    manager = SwarmRecoveryManager()
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("task-1", {"work": "compile"}))

    capture = bridge.capture("run-1", "outer-worker", manager, runtime)
    loaded = bridge.load("run-1")

    assert capture.swarm_sequence == 1
    assert capture.checkpoint.state_version == RECOVERY_ARCHIVE_VERSION
    assert loaded is not None
    assert loaded.checkpoint.checkpoint_id == capture.checkpoint.checkpoint_id
    assert loaded.manager.status().checkpoints == 1
    restored = loaded.restore_runtime()
    assert restored is not None
    assert restored.task("task-1") is not None
    assert restored.task("task-1").payload == {"work": "compile"}
    assert store.get_run("run-1").worker_id == "outer-worker"


def test_persisted_swarm_leases_are_requeued_on_restore(tmp_path):
    _, bridge = make_bridge(tmp_path)
    manager = SwarmRecoveryManager()
    runtime = SwarmRuntime(default_lease_seconds=300)
    runtime.register_worker("swarm-worker")
    runtime.submit(SwarmTask("task-1", {"work": "compile"}))
    leased = runtime.lease("swarm-worker")
    assert leased[0].state is TaskState.LEASED

    bridge.capture("run-1", "outer-worker", manager, runtime)
    restored = bridge.restore_runtime("run-1")

    assert restored is not None
    task = restored.task("task-1")
    assert task is not None
    assert task.state is TaskState.QUEUED
    assert task.leased_to is None
    assert task.lease_deadline is None


def test_swarm_checkpoint_composes_with_outer_step_replay_boundary(tmp_path):
    store, bridge = make_bridge(tmp_path)
    manager = SwarmRecoveryManager()
    runtime = SwarmRuntime()

    store.start_step(
        "run-1",
        "outer-step-1",
        "swarm-wave",
        worker_id="outer-worker",
        effect_key="wave-1",
    )
    store.finish_step(
        "run-1",
        "outer-step-1",
        StepStatus.SUCCEEDED,
        worker_id="outer-worker",
        result={"wave": 1},
    )
    bridge.capture(
        "run-1",
        "outer-worker",
        manager,
        runtime,
        after_step_id="outer-step-1",
    )
    store.start_step(
        "run-1",
        "outer-step-2",
        "swarm-wave",
        worker_id="outer-worker",
        effect_key="wave-2",
    )

    loaded = bridge.load("run-1")

    assert loaded is not None
    assert loaded.checkpoint.after_step_id == "outer-step-1"
    assert [step.step_id for step in loaded.resume.replay_steps] == ["outer-step-2"]


def test_failed_durable_commit_rolls_back_new_swarm_checkpoint(tmp_path):
    store, bridge = make_bridge(tmp_path, max_payload_bytes=64)
    manager = SwarmRecoveryManager()
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("task-1", {"blob": "x" * 128}))

    with pytest.raises(PayloadTooLarge):
        bridge.capture("run-1", "outer-worker", manager, runtime)

    assert manager.store.latest() is None
    assert len(manager.store) == 0
    assert bridge.load("run-1") is None
    assert store.get_run("run-1").status.value == "running"


def test_wrong_outer_worker_rolls_back_swarm_checkpoint(tmp_path):
    _, bridge = make_bridge(tmp_path)
    manager = SwarmRecoveryManager()
    runtime = SwarmRuntime()

    with pytest.raises(StateConflict, match="does not own"):
        bridge.capture("run-1", "wrong-worker", manager, runtime)

    assert manager.store.latest() is None
    assert len(manager.store) == 0


def test_load_rejects_checkpoint_envelope_version_mismatch(tmp_path):
    store, bridge = make_bridge(tmp_path)
    archive = SwarmRecoveryManager().export_archive()
    store.checkpoint(
        "run-1",
        archive,
        worker_id="outer-worker",
        state_version=RECOVERY_ARCHIVE_VERSION + 1,
    )

    with pytest.raises(DurableSwarmError, match="unsupported durable swarm"):
        bridge.load("run-1")


def test_load_rejects_archive_version_disagreeing_with_envelope(tmp_path):
    store, bridge = make_bridge(tmp_path)
    archive = SwarmRecoveryManager().export_archive()
    archive["version"] = RECOVERY_ARCHIVE_VERSION + 1
    store.checkpoint(
        "run-1",
        archive,
        worker_id="outer-worker",
        state_version=RECOVERY_ARCHIVE_VERSION,
    )

    with pytest.raises(DurableSwarmError, match="envelope/archive"):
        bridge.load("run-1")


def test_load_wraps_corrupt_swarm_archive_validation(tmp_path):
    store, bridge = make_bridge(tmp_path)
    archive = SwarmRecoveryManager().export_archive()
    archive["archive_checksum"] = "0" * 64
    store.checkpoint(
        "run-1",
        archive,
        worker_id="outer-worker",
        state_version=RECOVERY_ARCHIVE_VERSION,
    )

    with pytest.raises(DurableSwarmError, match="invalid durable swarm recovery archive"):
        bridge.load("run-1")


def test_multiple_durable_captures_restore_latest_swarm_state(tmp_path):
    _, bridge = make_bridge(tmp_path)
    manager = SwarmRecoveryManager()
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("task-1", {"wave": 1}))
    bridge.capture("run-1", "outer-worker", manager, runtime)

    runtime.submit(SwarmTask("task-2", {"wave": 2}))
    second = bridge.capture("run-1", "outer-worker", manager, runtime)
    loaded = bridge.load("run-1")

    assert second.swarm_sequence == 2
    assert loaded is not None
    assert loaded.manager.status().latest_sequence == 2
    restored = loaded.restore_runtime()
    assert restored is not None
    assert {task.id for task in restored.tasks()} == {"task-1", "task-2"}


def test_missing_swarm_checkpoint_returns_none_without_mutation(tmp_path):
    store, bridge = make_bridge(tmp_path)

    assert bridge.load("run-1") is None
    assert bridge.restore_runtime("run-1") is None
    assert store.get_run("run-1").worker_id == "outer-worker"


def test_bridge_rejects_wrong_component_types(tmp_path):
    store, bridge = make_bridge(tmp_path)
    manager = SwarmRecoveryManager()
    runtime = SwarmRuntime()

    with pytest.raises(TypeError, match="manager"):
        bridge.persist("run-1", "outer-worker", object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="runtime"):
        bridge.capture(
            "run-1",
            "outer-worker",
            manager,
            object(),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="store"):
        SwarmDurableBridge(object())  # type: ignore[arg-type]

    assert store.get_run("run-1").worker_id == "outer-worker"
    assert runtime.snapshot().submitted == 0
