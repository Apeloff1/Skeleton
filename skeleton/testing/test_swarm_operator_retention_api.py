import pytest
from fastapi import HTTPException

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask
from skeleton.api import swarm_operator_routes as routes


def _succeed(runtime: HardenedSwarmRuntime, task_id: str) -> None:
    if runtime.worker("w") is None:
        runtime.register_worker("w", capacity=10)
    runtime.submit(SwarmTask(task_id, {}))
    runtime.lease("w", limit=1)
    runtime.succeed("w", task_id)


def test_prune_terminal_endpoint_reclaims_capacity() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=3)
    for task_id in ("one", "two", "three"):
        _succeed(runtime, task_id)

    result = routes.prune_terminal_tasks(keep_terminal=1, runtime=runtime)

    assert result["removed"] == 2
    assert result["planned"] == 2
    assert result["retained_terminal"] == 1
    assert result["capacity_after"]["resident"] == 1
    assert tuple(task.id for task in runtime.tasks()) == ("three",)


def test_prune_terminal_endpoint_is_idempotent() -> None:
    runtime = HardenedSwarmRuntime()
    _succeed(runtime, "done")
    first = routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)
    second = routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)
    assert first["removed"] == 1
    assert second["removed"] == 0


def test_prune_terminal_endpoint_rejects_runtime_without_forget_seam() -> None:
    runtime = SwarmRuntime()
    runtime.submit(SwarmTask("queued", {}))
    # No terminal task means no forget call and is safely a no-op.
    assert routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)["removed"] == 0

    runtime.register_worker("w")
    runtime.lease("w")
    runtime.succeed("w", "queued")
    with pytest.raises(HTTPException) as exc:
        routes.prune_terminal_tasks(keep_terminal=0, runtime=runtime)
    assert exc.value.status_code == 409
