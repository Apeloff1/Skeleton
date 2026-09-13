import asyncio

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.events import EventBus
from skeleton.frontier.execution import ExecutionPolicy


class Echo:
    name = "echo"
    capabilities = set()

    async def run(self, task, context=None):
        return task


@pytest.mark.asyncio
async def test_execution_events_form_a_correlated_chain_without_raw_task_data():
    events = EventBus()
    seen = []

    async def observe(event):
        seen.append(event)

    await events.subscribe("agent.started", observe)
    await events.subscribe("agent.completed", observe)
    runtime = AgentRuntime({"echo": Echo()}, events=events)
    result = await runtime.execute("echo", "private task", request_id="request")
    assert [event.topic for event in seen] == ["agent.started", "agent.completed"]
    assert all(event.correlation_id == result.request_id for event in seen)
    assert seen[1].causation_id == seen[0].event_id
    assert "private task" not in repr([dict(event.payload) for event in seen])
    assert "private task" not in repr(result.provenance.metadata)
    assert runtime.stats()["latency_ms"]["count"] == 1


@pytest.mark.asyncio
async def test_observer_failure_or_timeout_does_not_change_agent_success():
    events = EventBus()

    async def broken(event):
        raise RuntimeError("observer unavailable")

    async def blocked(event):
        await asyncio.Event().wait()

    await events.subscribe("agent.started", broken)
    await events.subscribe("agent.completed", blocked)
    runtime = AgentRuntime(
        {"echo": Echo()}, events=events, execution_policy=ExecutionPolicy(event_timeout=0.005)
    )
    result = await runtime.execute("echo", "work")
    assert result.succeeded
    assert runtime.stats()["event_failures"] == 2
    assert runtime.stats()["active"] == 0
