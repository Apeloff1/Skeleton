"""Adversarial contracts for VOL-016 durable agent supervisor authority."""

from __future__ import annotations

import math

import pytest

from skeleton.agents.durable_supervisor import (
    AgentResourceAccountingDrift,
    AgentResourceAccountingError,
    DurableAgentSupervisor,
    measure_agent_resources,
)
from skeleton.agents.swarm_quota import Quota, QuotaExceeded, QuotaLedger, Usage
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState
from skeleton.state import SQLiteRunStore, StateConflict


def make_store(tmp_path, *, clock=None) -> SQLiteRunStore:
    kwargs = {} if clock is None else {"clock": clock}
    return SQLiteRunStore(tmp_path / "agent-supervisor.sqlite3", **kwargs)


def test_open_materializes_owned_durable_runtime(tmp_path) -> None:
    store = make_store(tmp_path)
    supervisor = DurableAgentSupervisor.open(store, "agent-run", "supervisor-a")

    status = supervisor.status()

    assert status.run.status.value == "running"
    assert status.run.worker_id == "supervisor-a"
    assert status.runtime.queued == 0
    assert status.resources == Usage()
    assert status.recovery.checkpoints == 1
    assert supervisor.last_commit is not None
    assert supervisor.last_commit.swarm_sequence == 1


def test_live_supervisor_lease_fences_second_owner(tmp_path) -> None:
    now = [100.0]
    store = make_store(tmp_path, clock=lambda: now[0])
    DurableAgentSupervisor.open(
        store,
        "agent-run",
        "supervisor-a",
        lease_seconds=30,
        runtime_clock=lambda: now[0],
    )

    with pytest.raises(StateConflict, match="leased by another worker"):
        DurableAgentSupervisor.open(
            store,
            "agent-run",
            "supervisor-b",
            lease_seconds=30,
            runtime_clock=lambda: now[0],
        )


def test_restart_requeues_persisted_agent_lease_and_reconciles_resources(tmp_path) -> None:
    now = [10.0]
    store = make_store(tmp_path, clock=lambda: now[0])
    first = DurableAgentSupervisor.open(
        store,
        "agent-run",
        "supervisor-a",
        lease_seconds=5,
        runtime_clock=lambda: now[0],
    )
    first.register_worker("worker", capacity=1)
    first.submit(SwarmTask("task-1", {"work": "compile"}))
    leased = first.lease("worker")
    assert leased[0].state is TaskState.LEASED
    assert first.status().resources.leased == 1

    now[0] = 16.0
    recovered = DurableAgentSupervisor.open(
        store,
        "agent-run",
        "supervisor-b",
        lease_seconds=5,
        runtime_clock=lambda: now[0],
    )

    task = recovered.runtime.task("task-1")
    assert task is not None
    assert task.state is TaskState.QUEUED
    assert task.leased_to is None
    assert task.lease_deadline is None
    assert recovered.status().resources == Usage(
        queued=1,
        leased=0,
        payload_bytes=len(b'{"work":"compile"}'),
    )
    assert recovered.status().recovery.latest_sequence is not None
    assert recovered.status().recovery.latest_sequence > first.status().recovery.latest_sequence


def test_queue_quota_rejection_does_not_mutate_authoritative_runtime(tmp_path) -> None:
    store = make_store(tmp_path)
    supervisor = DurableAgentSupervisor.open(
        store,
        "agent-run",
        "supervisor-a",
        quota=Quota(max_queued=1, max_leased=10, max_payload_bytes=10_000),
    )
    supervisor.submit(SwarmTask("task-1", {"n": 1}))
    before = supervisor.last_commit

    with pytest.raises(QuotaExceeded, match="queued quota exceeded"):
        supervisor.submit(SwarmTask("task-2", {"n": 2}))

    assert supervisor.runtime.task("task-2") is None
    assert supervisor.runtime.task("task-1") is not None
    assert supervisor.status().resources.queued == 1
    assert supervisor.last_commit == before


def test_lease_quota_rejection_is_copy_on_write(tmp_path) -> None:
    store = make_store(tmp_path)
    supervisor = DurableAgentSupervisor.open(
        store,
        "agent-run",
        "supervisor-a",
        quota=Quota(max_queued=10, max_leased=1, max_payload_bytes=10_000),
    )
    supervisor.register_worker("worker-a")
    supervisor.register_worker("worker-b")
    supervisor.submit(SwarmTask("task-a", {"n": "a"}))
    supervisor.submit(SwarmTask("task-b", {"n": "b"}))
    supervisor.lease("worker-a")

    with pytest.raises(QuotaExceeded, match="leased quota exceeded"):
        supervisor.lease("worker-b")

    assert supervisor.status().runtime.leased == 1
    assert supervisor.status().runtime.queued == 1
    assert supervisor.runtime.worker("worker-b") is not None
    assert supervisor.runtime.worker("worker-b").active == set()


def test_failed_durable_commit_rolls_back_accounting_and_runtime(
    tmp_path, monkeypatch
) -> None:
    store = make_store(tmp_path)
    supervisor = DurableAgentSupervisor.open(store, "agent-run", "supervisor-a")
    before_usage = supervisor.status().resources
    before_commit = supervisor.last_commit

    def fail_capture(*args, **kwargs):
        raise RuntimeError("durable storage unavailable")

    monkeypatch.setattr(supervisor.bridge, "capture", fail_capture)

    with pytest.raises(RuntimeError, match="durable storage unavailable"):
        supervisor.submit(SwarmTask("task-1", {"write": True}))

    assert supervisor.runtime.task("task-1") is None
    assert supervisor.status().resources == before_usage
    assert supervisor.last_commit == before_commit


def test_external_quota_writer_is_detected_as_accounting_drift(tmp_path) -> None:
    store = make_store(tmp_path)
    ledger = QuotaLedger()
    supervisor = DurableAgentSupervisor.open(
        store,
        "agent-run",
        "supervisor-a",
        ledger=ledger,
    )
    ledger.reserve(supervisor.resource_scope, queued=1)
    before_commit = supervisor.last_commit

    with pytest.raises(
        AgentResourceAccountingDrift,
        match="changed outside durable agent supervisor",
    ):
        supervisor.checkpoint()

    assert supervisor.last_commit == before_commit


def test_non_finite_payload_fails_before_authoritative_commit(tmp_path) -> None:
    store = make_store(tmp_path)
    supervisor = DurableAgentSupervisor.open(store, "agent-run", "supervisor-a")

    with pytest.raises(AgentResourceAccountingError, match="finite canonical JSON"):
        supervisor.submit(SwarmTask("nan-task", {"score": math.nan}))

    assert supervisor.runtime.task("nan-task") is None
    assert supervisor.status().resources == Usage()


def test_payload_accounting_includes_terminal_resident_tasks(tmp_path) -> None:
    store = make_store(tmp_path)
    supervisor = DurableAgentSupervisor.open(store, "agent-run", "supervisor-a")
    supervisor.register_worker("worker")
    supervisor.submit(SwarmTask("task-1", {"blob": "abc"}))
    supervisor.lease("worker")
    supervisor.succeed("worker", "task-1")

    measured = measure_agent_resources(supervisor.runtime)

    assert measured.queued == 0
    assert measured.leased == 0
    assert measured.resident_tasks == 1
    assert measured.payload_bytes == len(b'{"blob":"abc"}')
    assert supervisor.status().resources.payload_bytes == measured.payload_bytes


def test_worker_mutations_and_expired_lease_reap_are_durable(tmp_path) -> None:
    runtime_now = [50.0]
    store_now = [50.0]
    store = make_store(tmp_path, clock=lambda: store_now[0])
    supervisor = DurableAgentSupervisor.open(
        store,
        "agent-run",
        "supervisor-a",
        lease_seconds=300,
        runtime_clock=lambda: runtime_now[0],
    )
    supervisor.register_worker("worker")
    supervisor.submit(SwarmTask("task-1", {}, max_attempts=2))
    supervisor.lease("worker")
    runtime_now[0] = 100.0

    assert supervisor.reap_expired() == 1
    task = supervisor.runtime.task("task-1")
    assert task is not None
    assert task.state is TaskState.QUEUED
    assert task.attempts == 1
    assert supervisor.status().resources.queued == 1
    assert supervisor.status().resources.leased == 0


def test_measurement_rejects_non_runtime() -> None:
    with pytest.raises(TypeError, match="SwarmRuntime"):
        measure_agent_resources(object())  # type: ignore[arg-type]


def test_open_rejects_invalid_checkpoint_capacity(tmp_path) -> None:
    store = make_store(tmp_path)

    with pytest.raises(ValueError, match="max_checkpoints"):
        DurableAgentSupervisor.open(
            store,
            "agent-run",
            "supervisor-a",
            max_checkpoints=0,
        )


def test_runtime_measurement_matches_plain_swarm_state() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("queued", {"x": 1}))
    runtime.register_worker("worker")
    runtime.lease("worker")

    measured = measure_agent_resources(runtime)

    assert measured.queued == 0
    assert measured.leased == 1
    assert measured.resident_tasks == 1
    assert measured.payload_bytes == len(b'{"x":1}')
