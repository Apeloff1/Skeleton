"""Regression tests for agent-pool coordination lifecycle."""

import asyncio

from skeleton.agents.coordination import AgentPool, Coordinator, Task, TaskStatus
from skeleton.frontier.model_runtime import CancellationToken
from skeleton.frontier.orchestration import RunStatus, StepKind, StepStatus


def test_failed_handler_releases_agent_capacity() -> None:
    pool = AgentPool(max_agents=1)
    pool.create({"work"}, capacity=1)
    coordinator = Coordinator(pool=pool)

    def fail(_task):
        raise RuntimeError("boom")

    coordinator.register_handler("work", fail)

    first = coordinator.dispatch("first", task_type="work")
    assert first.status is TaskStatus.FAILED
    assert first.error == "boom"
    assert pool.stats()["total_load"] == 0

    second = coordinator.dispatch("second", task_type="work")
    assert second.status is TaskStatus.FAILED
    assert second.error == "boom"
    assert pool.stats()["total_load"] == 0
    assert pool.stats()["tasks_assigned"] == 2


def test_successful_handler_still_releases_agent_capacity() -> None:
    pool = AgentPool(max_agents=1)
    pool.create({"work"}, capacity=1)
    coordinator = Coordinator(pool=pool)
    coordinator.register_handler("work", lambda task: f"done:{task.description}")

    task = coordinator.dispatch("job", task_type="work")

    assert task.status is TaskStatus.COMPLETED
    assert task.result == "done:job"
    assert pool.stats()["total_load"] == 0


def test_handler_execution_uses_canonical_orchestration_lifecycle() -> None:
    pool = AgentPool(max_agents=1)
    pool.create({"work"}, capacity=1)
    coordinator = Coordinator(pool=pool)
    coordinator.register_handler("work", lambda task: f"done:{task.description}")

    task = coordinator.dispatch("job", task_type="work")
    run = coordinator.get_run(task.task_id)

    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert run.output == "done:job"
    assert [step.kind for step in run.steps] == [
        StepKind.MODEL,
        StepKind.TOOL,
        StepKind.MODEL,
    ]
    assert all(step.status is StepStatus.SUCCEEDED for step in run.steps)


def test_async_handler_uses_same_canonical_lifecycle() -> None:
    async def run_case() -> None:
        pool = AgentPool(max_agents=1)
        pool.create({"work"}, capacity=1)
        coordinator = Coordinator(pool=pool)

        async def handler(task):
            await asyncio.sleep(0)
            return f"async:{task.description}"

        coordinator.register_handler("work", handler)
        task = await coordinator.dispatch_async("job", task_type="work")
        run = coordinator.get_run(task.task_id)

        assert task.status is TaskStatus.COMPLETED
        assert task.result == "async:job"
        assert pool.stats()["total_load"] == 0
        assert run is not None
        assert run.status is RunStatus.COMPLETED

    asyncio.run(run_case())


def test_precancelled_handler_cancels_task_and_releases_capacity() -> None:
    async def run_case() -> None:
        pool = AgentPool(max_agents=1)
        pool.create({"work"}, capacity=1)
        coordinator = Coordinator(pool=pool)
        coordinator.register_handler("work", lambda task: task.description)
        cancellation = CancellationToken()
        cancellation.cancel()

        task = await coordinator.dispatch_async(
            "job",
            task_type="work",
            cancellation=cancellation,
        )
        run = coordinator.get_run(task.task_id)

        assert task.status is TaskStatus.CANCELLED
        assert task.error == "run cancelled before start"
        assert pool.stats()["total_load"] == 0
        assert run is not None
        assert run.status is RunStatus.CANCELLED
        assert run.steps == []

    asyncio.run(run_case())


def test_find_capable_skips_saturated_agents() -> None:
    pool = AgentPool(max_agents=2)
    saturated = pool.create({"work"}, capacity=1)
    available = pool.create({"work"}, capacity=2)
    blocker = Task(task_id="blocker", description="hold saturated agent")

    assert pool.assign(saturated, blocker) is True

    assert pool.find_capable("work") == [available]


def test_dispatch_routes_to_available_agent_when_peer_is_saturated() -> None:
    pool = AgentPool(max_agents=2)
    saturated = pool.create({"work"}, capacity=1)
    available = pool.create({"work"}, capacity=2)
    blocker = Task(task_id="blocker", description="hold saturated agent")
    assert pool.assign(saturated, blocker) is True

    coordinator = Coordinator(pool=pool)
    coordinator.register_handler("work", lambda task: f"done:{task.description}")

    task = coordinator.dispatch("job", task_type="work")

    assert task.status is TaskStatus.COMPLETED
    assert task.agent_id == available
    assert task.result == "done:job"
    assert pool.stats()["active"] == 2


def test_dispatch_expands_pool_when_all_capable_agents_are_saturated() -> None:
    pool = AgentPool(max_agents=2)
    saturated = pool.create({"work"}, capacity=1)
    blocker = Task(task_id="blocker", description="hold saturated agent")
    assert pool.assign(saturated, blocker) is True

    coordinator = Coordinator(pool=pool)
    coordinator.register_handler("work", lambda task: f"done:{task.description}")

    task = coordinator.dispatch("job", task_type="work")

    assert task.status is TaskStatus.COMPLETED
    assert task.agent_id != saturated
    assert task.result == "done:job"
    assert pool.stats()["active"] == 2
