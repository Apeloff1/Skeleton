"""Regression tests for agent-pool coordination lifecycle."""

import asyncio

import pytest

from skeleton.agents.coordination import AgentPool, Coordinator, Task, TaskStatus
from skeleton.frontier.orchestration import RunStatus, StepKind, StepStatus


def test_failed_handler_releases_agent_capacity_without_persisting_message() -> None:
    pool = AgentPool(max_agents=1)
    pool.create({"work"}, capacity=1)
    coordinator = Coordinator(pool=pool)
    sensitive_message = "api-key=super-secret-handler-detail"

    def fail(_task):
        raise RuntimeError(sensitive_message)

    coordinator.register_handler("work", fail)

    first = coordinator.dispatch("first", task_type="work")
    assert first.status is TaskStatus.FAILED
    assert first.error == "ToolExecutionError: tool 'work' failed with RuntimeError"
    assert sensitive_message not in first.error
    assert pool.stats()["total_load"] == 0

    first_run = coordinator.get_run_record(first.task_id)
    assert first_run is not None
    assert first_run.status is RunStatus.FAILED
    assert first_run.error == first.error
    assert sensitive_message not in first_run.error
    assert first_run.steps[-1].kind is StepKind.TOOL
    assert first_run.steps[-1].status is StepStatus.FAILED
    assert first_run.steps[-1].error == first.error
    assert sensitive_message not in first_run.steps[-1].error

    second = coordinator.dispatch("second", task_type="work")
    assert second.status is TaskStatus.FAILED
    assert second.error == "ToolExecutionError: tool 'work' failed with RuntimeError"
    assert sensitive_message not in second.error
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


def test_assign_rejects_duplicate_running_task_without_leaking_capacity() -> None:
    pool = AgentPool(max_agents=2)
    first_agent = pool.create({"work"}, capacity=2)
    second_agent = pool.create({"work"}, capacity=2)
    task = Task(task_id="job", description="single unit of work")

    assert pool.assign(first_agent, task) is True
    assert pool.assign(first_agent, task) is False
    assert pool.assign(second_agent, task) is False
    assert pool.stats()["tasks_assigned"] == 1
    assert pool.stats()["total_load"] == 1

    pool.release(first_agent, task.task_id)
    assert pool.stats()["total_load"] == 0


def test_assign_rejects_distinct_task_objects_with_same_id() -> None:
    pool = AgentPool(max_agents=2)
    first_agent = pool.create({"work"}, capacity=2)
    second_agent = pool.create({"work"}, capacity=2)
    first = Task(task_id="shared", description="original")
    duplicate = Task(task_id="shared", description="duplicate object")

    assert pool.assign(first_agent, first) is True
    assert pool.assign(second_agent, duplicate) is False
    assert duplicate.status is TaskStatus.PENDING
    assert duplicate.agent_id is None
    assert pool.stats()["tasks_assigned"] == 1
    assert pool.stats()["total_load"] == 1

    # A non-owner must not be able to free another agent's slot.
    pool.release(second_agent, first.task_id)
    assert pool.stats()["total_load"] == 1

    pool.release(first_agent, first.task_id)
    assert pool.stats()["total_load"] == 0

    # Once the real owner releases the ID, a fresh logical task can use it.
    replacement = Task(task_id="shared", description="replacement")
    assert pool.assign(second_agent, replacement) is True
    assert pool.stats()["total_load"] == 1
    pool.release(second_agent, replacement.task_id)
    assert pool.stats()["total_load"] == 0


def test_destroy_releases_task_id_ownership() -> None:
    pool = AgentPool(max_agents=2)
    first_agent = pool.create({"work"}, capacity=1)
    task = Task(task_id="shared", description="owned")
    assert pool.assign(first_agent, task) is True

    pool.destroy(first_agent)

    second_agent = pool.create({"work"}, capacity=1)
    replacement = Task(task_id="shared", description="replacement")
    assert pool.assign(second_agent, replacement) is True
    assert pool.stats()["total_load"] == 1


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


def test_async_dispatch_uses_same_canonical_run() -> None:
    pool = AgentPool(max_agents=1)
    pool.create({"work"}, capacity=1)
    coordinator = Coordinator(pool=pool)
    coordinator.register_handler("work", lambda task: task.description.upper())

    async def scenario():
        return await coordinator.dispatch_async("job", task_type="work")

    task = asyncio.run(scenario())

    assert task.status is TaskStatus.COMPLETED
    assert task.result == "JOB"
    assert pool.stats()["total_load"] == 0
    run = coordinator.get_run_record(task.task_id)
    assert run is not None
    assert run.status is RunStatus.COMPLETED


def test_sync_registered_dispatch_fails_before_mutation_inside_event_loop() -> None:
    coordinator = Coordinator()
    coordinator.register_handler("work", lambda task: task.description)

    async def scenario():
        with pytest.raises(RuntimeError, match="use await dispatch_async"):
            coordinator.dispatch("job", task_type="work")

    asyncio.run(scenario())

    assert coordinator.list_tasks() == []
    assert coordinator.stats()["total"] == 0


def test_unhandled_task_preserves_external_running_compatibility() -> None:
    coordinator = Coordinator()

    task = coordinator.dispatch("external", task_type="remote")

    assert task.status is TaskStatus.RUNNING
    assert task.agent_id is not None
    assert coordinator.get_run_record(task.task_id) is None


def test_agent_pool_rejects_invalid_capacity_configuration() -> None:
    for value in (0, -1, True, 1.5):
        with pytest.raises((TypeError, ValueError)):
            AgentPool(max_agents=value)  # type: ignore[arg-type]

    pool = AgentPool(max_agents=1)
    for value in (0, -1, False, 1.5):
        with pytest.raises((TypeError, ValueError)):
            pool.create({"work"}, capacity=value)  # type: ignore[arg-type]


def test_register_handler_rejects_non_callable_before_tool_registration() -> None:
    coordinator = Coordinator()

    with pytest.raises(TypeError, match="handler must be callable"):
        coordinator.register_handler("work", None)  # type: ignore[arg-type]

    assert coordinator.list_tasks() == []


def test_failed_fresh_agent_assignment_does_not_leak_pool_slot() -> None:
    class RejectingPool(AgentPool):
        def assign(self, agent_id: str, task: Task) -> bool:
            return False

    pool = RejectingPool(max_agents=1)
    coordinator = Coordinator(pool=pool)

    task = coordinator.dispatch("job", task_type="work")

    assert task.status is TaskStatus.FAILED
    assert task.error == "New agent could not accept task"
    assert pool.stats()["active"] == 0
    assert pool.stats()["created"] == 1
    assert pool.stats()["destroyed"] == 1


def test_dispatch_copies_metadata_from_caller() -> None:
    metadata = {"request": "original"}
    coordinator = Coordinator()

    task = coordinator.dispatch("job", task_type="remote", metadata=metadata)
    metadata["request"] = "mutated"

    assert task.status is TaskStatus.RUNNING
    assert task.metadata == {"request": "original"}
