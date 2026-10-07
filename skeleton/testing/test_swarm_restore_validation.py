import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_restore import validate_restore_state
from skeleton.agents.swarm_runtime import SwarmTask


def _state() -> dict[str, object]:
    runtime = HardenedSwarmRuntime(max_tasks=4, max_workers=2)
    runtime.register_worker("w", capacity=2)
    runtime.submit(SwarmTask("t", {}))
    return runtime.export_state()


def test_rejects_unknown_snapshot_version() -> None:
    state = _state()
    state["version"] = 99
    with pytest.raises(ValueError, match="unsupported"):
        validate_restore_state(state)


def test_rejects_duplicate_task_ids() -> None:
    state = _state()
    state["tasks"] = [state["tasks"][0], dict(state["tasks"][0])]
    with pytest.raises(ValueError, match="duplicate task"):
        validate_restore_state(state)


def test_rejects_duplicate_worker_ids() -> None:
    state = _state()
    state["workers"] = [state["workers"][0], dict(state["workers"][0])]
    with pytest.raises(ValueError, match="duplicate worker"):
        validate_restore_state(state)


def test_rejects_snapshot_above_capacity() -> None:
    state = _state()
    state["config"]["max_tasks"] = 1
    state["tasks"].append({"id": "extra", "payload": {}, "state": "queued", "max_attempts": 1, "attempts": 0})
    with pytest.raises(ValueError, match="max_tasks"):
        validate_restore_state(state)


def test_rejects_non_leased_task_with_owner() -> None:
    state = _state()
    state["tasks"][0]["leased_to"] = "w"
    with pytest.raises(ValueError, match="non-leased"):
        validate_restore_state(state)


def test_rejects_leased_task_with_missing_worker() -> None:
    state = _state()
    task = state["tasks"][0]
    task["state"] = "leased"
    task["leased_to"] = "ghost"
    task["lease_deadline"] = 1.0
    with pytest.raises(ValueError, match="missing worker"):
        validate_restore_state(state)


def test_restore_requeues_leases_and_resets_worker_liveness() -> None:
    clock = [10.0]
    runtime = HardenedSwarmRuntime(clock=lambda: clock[0])
    runtime.register_worker("w")
    runtime.submit(SwarmTask("t", {}))
    runtime.lease("w")
    state = runtime.export_state()
    clock[0] = 100.0
    restored = HardenedSwarmRuntime.from_state(state, clock=lambda: clock[0], requeue_leased=True)
    assert restored.task("t").state.value == "queued"
    assert restored.worker("w").active == set()
    assert restored.worker("w").last_seen == 100.0
