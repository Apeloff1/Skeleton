import asyncio

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.execution import RuntimeClosed
from skeleton.testing.test_frontier_runtime_limits import BlockingAgent, runtime


@pytest.mark.asyncio
async def test_graceful_shutdown_drains_active_and_previously_queued_requests():
    agent = BlockingAgent()
    instance = runtime(agent, max_concurrency=1)
    first = asyncio.create_task(instance.execute(agent.name, "one"))
    await agent.started.wait()
    second = asyncio.create_task(instance.execute(agent.name, "two"))
    await asyncio.sleep(0)
    close = asyncio.create_task(instance.aclose())
    await asyncio.sleep(0)
    with pytest.raises(RuntimeClosed):
        await instance.execute(agent.name, "late")
    agent.release.set()
    assert all(result.succeeded for result in await asyncio.gather(first, second))
    await close
    assert instance.stats()["active"] == instance.stats()["queued"] == 0
    await instance.aclose()


@pytest.mark.asyncio
async def test_shutdown_cancels_work_after_grace_period():
    agent = BlockingAgent()
    instance = runtime(agent)
    pending = asyncio.create_task(instance.execute(agent.name, "hang"))
    await agent.started.wait()
    await instance.aclose(grace_period=0.01)
    assert pending.cancelled()
    assert instance.stats()["active"] == 0


@pytest.mark.asyncio
async def test_context_manager_closes_on_exception():
    instance = AgentRuntime()
    with pytest.raises(ValueError):
        async with instance:
            raise ValueError("caller failed")
    assert instance.stats()["closed"]


@pytest.mark.asyncio
async def test_invalid_output_is_removed_from_failed_result():
    class InvalidAgent:
        name = "invalid"
        capabilities = set()

        async def run(self, task, context=None):
            return object()

    instance = AgentRuntime({"invalid": InvalidAgent()})
    result = await instance.execute("invalid", "work")
    assert not result.succeeded
    assert result.as_dict()["output"] is None
