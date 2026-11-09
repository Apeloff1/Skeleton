from __future__ import annotations

import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_runtime import SwarmRuntime, TaskState
from skeleton.api.swarm_routes import (
    FailureReport,
    TaskSubmission,
    WorkerRegistration,
    complete_task,
    events,
    fail_task,
    get_task,
    get_worker,
    lease_tasks,
    reap_expired,
    register_worker,
    submit_task,
    swarm_status,
    unregister_worker,
)


def test_full_submit_lease_complete_flow() -> None:
    runtime = SwarmRuntime()
    worker = register_worker(
        WorkerRegistration(worker_id="builder-1", capabilities=["python", "tests"], capacity=2),
        runtime,
    )
    assert worker["available"] == 2

    admitted = submit_task(
        TaskSubmission(
            task_id="compile-1",
            payload={"repo": "skeleton"},
            priority=7,
            required_capabilities=["python"],
        ),
        runtime,
    )
    assert admitted["state"] == "queued"

    leased = lease_tasks("builder-1", None, runtime)
    assert [item["id"] for item in leased["tasks"]] == ["compile-1"]
    assert leased["tasks"][0]["state"] == "leased"

    completed = complete_task("builder-1", "compile-1", runtime)
    assert completed["state"] == "succeeded"
    assert swarm_status(runtime)["succeeded"] == 1


def test_capability_routing_is_visible_through_api() -> None:
    runtime = SwarmRuntime()
    register_worker(WorkerRegistration(worker_id="cpu", capabilities=["cpu"], capacity=4), runtime)
    submit_task(
        TaskSubmission(task_id="gpu", required_capabilities=["gpu"], priority=1),
        runtime,
    )
    submit_task(
        TaskSubmission(task_id="cpu", required_capabilities=["cpu"], priority=2),
        runtime,
    )

    leased = lease_tasks("cpu", 4, runtime)

    assert [task["id"] for task in leased["tasks"]] == ["cpu"]
    assert get_task("gpu", runtime)["state"] == "queued"


def test_failure_report_requeues_then_dead_letters() -> None:
    runtime = SwarmRuntime()
    register_worker(WorkerRegistration(worker_id="w"), runtime)
    submit_task(TaskSubmission(task_id="job", max_attempts=2), runtime)

    lease_tasks("w", None, runtime)
    retry = fail_task("w", "job", FailureReport(error="first"), runtime)
    assert retry["state"] == "queued"

    lease_tasks("w", None, runtime)
    dead = fail_task("w", "job", FailureReport(error="second"), runtime)
    assert dead["state"] == "dead"
    assert dead["last_error"] == "second"


def test_duplicate_task_maps_to_conflict() -> None:
    runtime = SwarmRuntime()
    body = TaskSubmission(task_id="same")
    submit_task(body, runtime)

    with pytest.raises(HTTPException) as exc:
        submit_task(body, runtime)

    assert exc.value.status_code == 409


def test_unknown_worker_maps_to_not_found_on_lease() -> None:
    runtime = SwarmRuntime()

    with pytest.raises(HTTPException) as exc:
        lease_tasks("missing", None, runtime)

    assert exc.value.status_code == 404


def test_foreign_completion_maps_to_conflict() -> None:
    runtime = SwarmRuntime()
    register_worker(WorkerRegistration(worker_id="owner"), runtime)
    register_worker(WorkerRegistration(worker_id="other"), runtime)
    submit_task(TaskSubmission(task_id="job"), runtime)
    lease_tasks("owner", None, runtime)

    with pytest.raises(HTTPException) as exc:
        complete_task("other", "job", runtime)

    assert exc.value.status_code == 409


def test_unregister_worker_requeues_active_tasks() -> None:
    runtime = SwarmRuntime()
    register_worker(WorkerRegistration(worker_id="w", capacity=2), runtime)
    submit_task(TaskSubmission(task_id="a"), runtime)
    submit_task(TaskSubmission(task_id="b"), runtime)
    lease_tasks("w", None, runtime)

    result = unregister_worker("w", True, runtime)

    assert result == {"worker_id": "w", "released": 2, "requeued": True}
    assert swarm_status(runtime)["queued"] == 2


def test_worker_and_task_serialization_are_json_safe() -> None:
    runtime = SwarmRuntime()
    register_worker(WorkerRegistration(worker_id="w", capabilities=["z", "a"]), runtime)
    submit_task(TaskSubmission(task_id="t", required_capabilities=["z", "a"]), runtime)

    worker = get_worker("w", runtime)
    task = get_task("t", runtime)

    assert worker["capabilities"] == ["a", "z"]
    assert task["required_capabilities"] == ["a", "z"]
    assert task["state"] == TaskState.QUEUED.value


def test_reap_and_event_feed_are_bounded_api_surfaces() -> None:
    runtime = SwarmRuntime()
    register_worker(WorkerRegistration(worker_id="w"), runtime)
    submit_task(TaskSubmission(task_id="t"), runtime)

    result = reap_expired(runtime)
    feed = events(2, runtime)

    assert result["expired"] == 0
    assert len(feed["events"]) == 2
    assert feed["events"][-1]["kind"] == "task.submitted"
