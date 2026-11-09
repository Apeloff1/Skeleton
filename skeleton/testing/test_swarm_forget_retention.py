import pytest

from skeleton.agents.swarm_hardened import HardenedSwarmRuntime
from skeleton.agents.swarm_retention import RetentionPolicy, prune_terminal
from skeleton.agents.swarm_runtime import AdmissionError, SwarmTask, TaskState


def _succeeded(runtime: HardenedSwarmRuntime, task_id: str) -> None:
    if runtime.worker("w") is None:
        runtime.register_worker("w", capacity=10)
    runtime.submit(SwarmTask(task_id, {}))
    leased = runtime.lease("w", limit=1)
    assert leased and leased[0].id == task_id
    runtime.succeed("w", task_id)


def test_forget_reclaims_terminal_capacity() -> None:
    runtime = HardenedSwarmRuntime(max_tasks=1)
    _succeeded(runtime, "old")
    with pytest.raises(AdmissionError):
        runtime.submit(SwarmTask("new", {}))

    assert runtime.forget("old") is True
    admitted = runtime.submit(SwarmTask("new", {}))
    assert admitted.id == "new"
    assert runtime.task("old") is None


def test_forget_is_idempotent_for_unknown_terminal_id() -> None:
    runtime = HardenedSwarmRuntime()
    assert runtime.forget("missing") is False


def test_forget_rejects_queued_and_leased_work() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("queued", {}))
    with pytest.raises(AdmissionError):
        runtime.forget("queued")

    runtime.register_worker("w")
    runtime.lease("w")
    with pytest.raises(AdmissionError):
        runtime.forget("queued")


def test_forget_updates_snapshot_and_events() -> None:
    runtime = HardenedSwarmRuntime()
    _succeeded(runtime, "done")
    assert runtime.snapshot().succeeded == 1

    runtime.forget("done")

    assert runtime.snapshot().succeeded == 0
    assert any(kind == "task.forgotten" and subject == "done" for _, kind, subject in runtime.events())


def test_retention_policy_prunes_oldest_terminal_residents() -> None:
    runtime = HardenedSwarmRuntime()
    for task_id in ("one", "two", "three"):
        _succeeded(runtime, task_id)

    plan = RetentionPolicy(max_terminal_tasks=1).plan(runtime)
    assert plan.removable == ("one", "two")
    assert plan.retained == 1
    assert plan.terminal == 3
    assert prune_terminal(runtime, plan.removable) == 2
    assert tuple(task.id for task in runtime.tasks()) == ("three",)
    assert runtime.snapshot().succeeded == 1


def test_cancelled_and_dead_tasks_can_be_forgotten() -> None:
    runtime = HardenedSwarmRuntime()
    runtime.submit(SwarmTask("cancelled", {}))
    runtime.cancel("cancelled")
    assert runtime.task("cancelled").state is TaskState.CANCELLED
    assert runtime.forget("cancelled") is True

    runtime.register_worker("w")
    runtime.submit(SwarmTask("dead", {}, max_attempts=1))
    runtime.lease("w")
    runtime.fail("w", "dead", "fatal")
    assert runtime.task("dead").state is TaskState.DEAD
    assert runtime.forget("dead") is True
