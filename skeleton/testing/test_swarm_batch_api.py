import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.api.swarm_batch_routes import BatchSubmission, BatchTask, submit


def test_batch_api_admits_complete_batch() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=10)
    result = submit(
        BatchSubmission(tasks=[BatchTask(task_id="a"), BatchTask(task_id="b")]),
        runtime=runtime,
    )
    assert result == {"task_ids": ["a", "b"], "admitted": 2}


def test_batch_api_is_all_or_none_on_duplicate() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=10)
    runtime.submit_many([])
    with pytest.raises(HTTPException) as exc:
        submit(
            BatchSubmission(tasks=[BatchTask(task_id="a"), BatchTask(task_id="a")]),
            runtime=runtime,
        )
    assert exc.value.status_code == 409
    assert runtime.tasks() == ()


def test_batch_api_rejects_capacity_overcommit_without_partial_state() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=1)
    with pytest.raises(HTTPException) as exc:
        submit(
            BatchSubmission(tasks=[BatchTask(task_id="a"), BatchTask(task_id="b")]),
            runtime=runtime,
        )
    assert exc.value.status_code == 409
    assert runtime.tasks() == ()
