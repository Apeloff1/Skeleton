"""Regression tests for agent-pool coordination lifecycle."""

from skeleton.agents.coordination import AgentPool, Coordinator, TaskStatus


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
