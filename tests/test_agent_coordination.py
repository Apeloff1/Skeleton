"""Regression tests for agent-pool coordination lifecycle."""

from skeleton.agents.coordination import AgentPool, Coordinator, Task, TaskStatus


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
    assert first.error == "RuntimeError: handler execution failed"
    assert sensitive_message not in first.error
    assert pool.stats()["total_load"] == 0

    second = coordinator.dispatch("second", task_type="work")
    assert second.status is TaskStatus.FAILED
    assert second.error == "RuntimeError: handler execution failed"
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
