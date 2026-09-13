from skeleton.agents.swarm_gc import capacity, compact_runtime
from skeleton.agents.swarm_runtime import SwarmRuntime, SwarmTask, TaskState


def _complete(runtime: SwarmRuntime, task_id: str) -> None:
    if runtime.worker("w") is None:
        runtime.register_worker("w")
    runtime.submit(SwarmTask(task_id, {}))
    runtime.lease("w")
    runtime.succeed("w", task_id)


def test_gc_reclaims_terminal_resident_capacity() -> None:
    runtime = SwarmRuntime(max_tasks=5)
    for i in range(5):
        _complete(runtime, str(i))
    assert capacity(runtime)["available"] == 0
    rebuilt, result = compact_runtime(runtime, keep_terminal=2)
    assert result.removed == 3
    assert capacity(rebuilt)["available"] == 3


def test_gc_preserves_live_tasks() -> None:
    runtime = SwarmRuntime(max_tasks=10)
    runtime.submit(SwarmTask("queued", {}))
    _complete(runtime, "done")
    rebuilt, _ = compact_runtime(runtime, keep_terminal=0)
    assert rebuilt.task("queued").state is TaskState.QUEUED
    assert rebuilt.task("done") is None


def test_gc_preserves_live_lease_when_requested_by_rebuild() -> None:
    runtime = SwarmRuntime(max_tasks=10)
    runtime.register_worker("w")
    runtime.submit(SwarmTask("leased", {}))
    runtime.lease("w")
    rebuilt, _ = compact_runtime(runtime, keep_terminal=0)
    task = rebuilt.task("leased")
    assert task.state is TaskState.LEASED
    assert task.leased_to == "w"
    assert "leased" in rebuilt.worker("w").active
