"""Regression tests for agent-pool coordination lifecycle."""

import asyncio

from skeleton.agents.coordination import AgentPool, Coordinator, Task, TaskStatus
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

    first_run = coordinator.get_run_record(first.task_id)
    assert first_run is not None
    assert first_run.status is RunStatus.FAILED
    assert [step.kind for step in first_run.steps] == [StepKind.MODEL, StepKind.TOOL]
    assert first_run.steps[-1].status is StepStatus.FAILED

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

    run = coordinator.get_run_record(task.task_id)
    assert run is not None
    assert run.status is RunStatus.COMPLETED
    assert run.output == "done:job"
    assert [step.kind for step in run.steps] == [
        StepKind.MODEL,
        StepKind.TOOL,
        StepKind.MODEL,
    ]
    assert all(step.status is StepStatus.SUCCEEDED for step in run.steps)


def test_dispatch_remains_compatible_inside_running_event_loop() -> None:
    pool = AgentPool(max_agents=1)
    pool.create({"work"}, capacity=1)
    coordinator = Coordinator(pool=pool)

    async def handler(task):
        await asyncio.sleep(0)
        return f"async:{task.description}"

    coordinator.register_handler("work", handler)

    async def exercise():
        return coordinator.dispatch("job", task_type="work")

    task = asyncio.run(exercise())

    assert task.status is TaskStatus.COMPLETED
    assert task.result == "async:job"
    assert pool.stats()["total_load"] == 0
    run = coordinator.get_run_record(task.task_id)
    assert run is not None
    assert run.status is RunStatus.COMPLETED


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
