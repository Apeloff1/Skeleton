from __future__ import annotations

import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState
from skeleton.api.swarm_routes import (
    CancelRequest,
    ReviveRequest,
    heartbeat,
    cancel_task,
    dead_letters,
    list_tasks,
    list_workers,
    renew_task,
    revive_task,
)


def test_worker_listing_and_heartbeat_surface_runtime_state() -> None:
    runtime = SwarmRuntime()
    runtime.register_worker("w", capabilities={"cpu"}, capacity=3)

    beat = heartbeat("w", runtime)
    listed = list_workers(runtime)

    assert beat["heartbeats"] == 1
    assert beat["available"] == 3
    assert listed["workers"][0]["id"] == "w"
    assert listed["workers"][0]["capabilities"] == ["cpu"]


def test_api_renew_cancel_and_revive_dead_letter_flow() -> None:
    runtime = SwarmRuntime(default_lease_seconds=5)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("job", {}, max_attempts=1))
    runtime.lease("w")

    renewed = renew_task("w", "job", 20, runtime)
    assert renewed["lease_deadline"] is not None

    runtime.fail("w", "job", "fatal")
    dead = dead_letters(runtime)
    assert [item["id"] for item in dead["tasks"]] == ["job"]

    revived = revive_task("job", ReviveRequest(reset_attempts=True), runtime)
    assert revived["state"] == "queued"
    assert revived["attempts"] == 0

    runtime.lease("w")
    cancelled = cancel_task("job", CancelRequest(reason="operator abort"), runtime)
    assert cancelled["state"] == "cancelled"
    assert cancelled["last_error"] == "operator abort"


def test_task_listing_can_filter_state() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("queued", {}))
    runtime.register_worker("w")
    runtime.submit(SwarmTask("done", {}))
    runtime.lease("w", limit=1)
    leased_id = next(task.id for task in runtime.tasks() if task.state is TaskState.LEASED)
    runtime.succeed("w", leased_id)

    queued = list_tasks("queued", runtime)
    succeeded = list_tasks("succeeded", runtime)

    assert all(task["state"] == "queued" for task in queued["tasks"])
    assert all(task["state"] == "succeeded" for task in succeeded["tasks"])


def test_unknown_worker_heartbeat_maps_to_not_found() -> None:
    with pytest.raises(HTTPException) as exc:
        heartbeat("missing", SwarmRuntime())
    assert exc.value.status_code == 404
