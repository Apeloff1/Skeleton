import asyncio

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.capabilities import CapabilityPolicy
from skeleton.frontier.execution import ExecutionPolicy, ExecutionStatus, RuntimeBusy


class BlockingAgent:
    name = "blocking"
    capabilities = {"work"}

    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def run(self, task, context=None):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return context


def runtime(agent, **limits):
    instance = AgentRuntime(
        policy=CapabilityPolicy.from_names({"work"}), execution_policy=ExecutionPolicy(**limits)
    )
    instance.register(agent)
    return instance


@pytest.mark.asyncio
async def test_no_capability_argument_does_not_bypass_authorization():
    agent = BlockingAgent()
    instance = AgentRuntime()
    instance.register(agent)
    with pytest.raises(PermissionError):
        await instance.execute(agent.name, "forbidden")
    assert agent.calls == 0


@pytest.mark.asyncio
async def test_capacity_and_cancellation_release_exactly_one_slot():
    agent = BlockingAgent()
    instance = runtime(agent, max_concurrency=1, max_queue=1)
    active = asyncio.create_task(instance.execute(agent.name, "active"))
    await agent.started.wait()
    waiting = asyncio.create_task(instance.execute(agent.name, "waiting"))
    await asyncio.sleep(0)
    assert instance.stats()["queued"] == 1
    with pytest.raises(RuntimeBusy):
        await instance.execute(agent.name, "overflow")
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    active.cancel()
    with pytest.raises(asyncio.CancelledError):
        await active
    assert instance.stats()["active"] == instance.stats()["queued"] == 0
    agent.release.set()
    assert (await instance.execute(agent.name, "next")).succeeded


@pytest.mark.asyncio
async def test_execution_timeout_returns_typed_result_and_releases_capacity():
    agent = BlockingAgent()
    instance = runtime(agent, execution_timeout=0.01)
    result = await instance.execute(agent.name, "timeout")
    assert result.status is ExecutionStatus.TIMED_OUT
    assert not result.succeeded
    assert result.elapsed_ms >= 0
    assert instance.stats()["active"] == 0
    agent.release.set()
    assert (await instance.execute(agent.name, "retry")).succeeded


@pytest.mark.asyncio
async def test_queue_timeout_never_dispatches_waiting_work():
    agent = BlockingAgent()
    instance = runtime(agent, max_concurrency=1, queue_timeout=0.01)
    first = asyncio.create_task(instance.execute(agent.name, "first"))
    await agent.started.wait()
    with pytest.raises(RuntimeBusy, match="queue deadline"):
        await instance.execute(agent.name, "waiting")
    assert agent.calls == 1
    agent.release.set()
    await first


@pytest.mark.asyncio
async def test_queued_context_is_detached_and_policy_is_rechecked():
    agent = BlockingAgent()
    instance = runtime(agent, max_concurrency=1)
    first = asyncio.create_task(instance.execute(agent.name, "first"))
    await agent.started.wait()
    context = {"nested": [1]}
    second = asyncio.create_task(instance.execute(agent.name, "second", context=context))
    await asyncio.sleep(0)
    context["nested"].append(2)
    agent.release.set()
    await first
    assert (await second).output == {"nested": [1]}
    agent.release.clear()
    first = asyncio.create_task(instance.execute(agent.name, "first"))
    await asyncio.sleep(0)
    second = asyncio.create_task(instance.execute(agent.name, "second"))
    await asyncio.sleep(0)
    instance.policy = CapabilityPolicy.from_names(())
    agent.release.set()
    await first
    with pytest.raises(PermissionError):
        await second
    assert instance.stats()["active"] == instance.stats()["queued"] == 0


def test_runtime_rejects_sync_agents_and_mutable_registry_writes():
    class SyncAgent:
        name = "sync"
        capabilities = set()

        def run(self, task, context=None):
            return task

    instance = AgentRuntime()
    with pytest.raises(TypeError, match="async"):
        instance.register(SyncAgent())
    with pytest.raises(TypeError):
        instance.agents["sync"] = SyncAgent()
