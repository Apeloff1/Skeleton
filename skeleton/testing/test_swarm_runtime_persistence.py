from __future__ import annotations

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def test_export_restore_round_trip_preserves_terminal_and_queued_work() -> None:
    runtime = SwarmRuntime(max_tasks=50, default_lease_seconds=17)
    runtime.register_worker("worker", capabilities={"cpu"}, capacity=2)
    runtime.submit(SwarmTask("done", {"x": 1}, required_capabilities=frozenset({"cpu"})))
    runtime.submit(SwarmTask("queued", {"x": 2}, priority=7))
    runtime.lease("worker", limit=1)
    runtime.succeed("worker", "done")

    state = runtime.export_state()
    restored = SwarmRuntime.from_state(state)

    assert restored.max_tasks == 50
    assert restored.default_lease_seconds == 17
    assert restored.task("done").state is TaskState.SUCCEEDED
    assert restored.task("queued").state is TaskState.QUEUED
    assert restored.worker("worker").capacity == 2
    assert restored.snapshot().submitted == 2


def test_restore_requeues_live_leases_by_default() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("worker")
    runtime.submit(SwarmTask("leased", {}))
    runtime.lease("worker")

    restored = SwarmRuntime.from_state(runtime.export_state())

    task = restored.task("leased")
    assert task.state is TaskState.QUEUED
    assert task.leased_to is None
    assert task.lease_deadline is None
    assert task.last_error == "restored lease requeued"
    assert restored.worker("worker").active == set()


def test_restore_can_preserve_live_lease_accounting() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("worker", capacity=2)
    runtime.submit(SwarmTask("leased", {}))
    runtime.lease("worker")

    restored = SwarmRuntime.from_state(runtime.export_state(), requeue_leased=False)

    assert restored.task("leased").state is TaskState.LEASED
    assert restored.task("leased").leased_to == "worker"
    assert restored.worker("worker").active == {"leased"}
    assert restored.worker("worker").available == 1


def test_exported_state_is_plain_serializable_shape() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("worker", capabilities={"gpu", "cpu"})
    runtime.submit(SwarmTask("job", {"nested": {"ok": True}}))

    state = runtime.export_state()

    assert state["version"] == 1
    assert isinstance(state["tasks"], list)
    assert isinstance(state["workers"], list)
    assert state["tasks"][0]["state"] == "queued"
    assert state["workers"][0]["capabilities"] == ["cpu", "gpu"]
