from fastapi import HTTPException

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmTask, TaskState
from skeleton.api.swarm_routes import RestoreRequest, dead_letters, list_tasks, list_workers, restore_state


def test_worker_listing_is_bounded_and_direct_call_safe() -> None:
    runtime = HardenedSwarmRuntime()
    for index in range(5):
        runtime.register_worker(f"w{index}")
    page = list_workers(offset=1, limit=2, runtime=runtime)
    assert page["total"] == 5
    assert [item["id"] for item in page["workers"]] == ["w1", "w2"]


def test_task_listing_filters_and_pages() -> None:
    runtime = HardenedSwarmRuntime()
    for index in range(5):
        runtime.submit(SwarmTask(f"t{index}", {}))
    page = list_tasks(state=TaskState.QUEUED, offset=2, limit=2, runtime=runtime)
    assert page["total"] == 5
    assert [item["id"] for item in page["tasks"]] == ["t2", "t3"]


def test_dead_letter_listing_is_bounded() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.register_worker("w", capacity=3)
    for index in range(3):
        runtime.submit(SwarmTask(f"t{index}", {}, max_attempts=1))
    for task in runtime.lease("w", limit=3):
        runtime.fail("w", task.id, "boom")
    page = dead_letters(limit=2, runtime=runtime)
    assert page["total"] == 3
    assert len(page["tasks"]) == 2


def test_restore_endpoint_rejects_duplicate_snapshot_ids() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("t", {}))
    state = runtime.export_state()
    state["tasks"].append(dict(state["tasks"][0]))
    try:
        restore_state(RestoreRequest(state=state))
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "duplicate task" in exc.detail
    else:
        raise AssertionError("invalid restore was accepted")
