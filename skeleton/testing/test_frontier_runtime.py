import asyncio

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.memory import InMemoryStore


class EchoAgent:
    name = "echo"
    capabilities = {"text.generate"}

    async def run(self, task, context=None):
        return {"task": task, "context": dict(context or {})}


class BrokenAgent:
    name = "broken"
    capabilities = {"text.generate"}

    async def run(self, task, context=None):
        raise RuntimeError("boom")


class CountingAgent:
    name = "counting"
    capabilities = {"text.generate"}

    def __init__(self):
        self.calls = 0

    async def run(self, task, context=None):
        self.calls += 1
        await asyncio.sleep(0)
        return {"task": task, "call": self.calls, "context": dict(context or {})}


class BlockingAgent:
    name = "blocking"
    capabilities = {"text.generate"}

    def __init__(self):
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, task, context=None):
        self.calls += 1
        self.started.set()
        await self.release.wait()
        return {"task": task, "call": self.calls}


@pytest.mark.asyncio
async def test_runtime_executes_with_capability_gate_and_provenance():
    runtime = AgentRuntime()
    runtime.register(EchoAgent())
    result = await runtime.execute(
        "echo", "build npc", context={"world": "frontier"}, required_capability="text.generate"
    )
    assert result.succeeded
    assert result.output["task"] == "build npc"
    assert result.provenance is not None
    assert result.provenance.operation == "agent.execute.completed"


@pytest.mark.asyncio
async def test_runtime_rejects_missing_capability():
    runtime = AgentRuntime()
    runtime.register(EchoAgent())
    with pytest.raises(PermissionError):
        await runtime.execute("echo", "build", required_capability="code.execute")


@pytest.mark.asyncio
async def test_runtime_contains_failures_as_results():
    runtime = AgentRuntime()
    runtime.register(BrokenAgent())
    result = await runtime.execute("broken", "fail safely")
    assert not result.succeeded
    assert "RuntimeError" in result.error


@pytest.mark.asyncio
async def test_runtime_idempotency_replays_completed_result_without_rerun():
    runtime = AgentRuntime()
    agent = CountingAgent()
    runtime.register(agent)

    first = await runtime.execute(
        "counting",
        "build once",
        context={"world": "frontier"},
        idempotency_key="job-42",
    )
    second = await runtime.execute(
        "counting",
        "build once",
        context={"world": "frontier"},
        idempotency_key="job-42",
    )

    assert first is second
    assert agent.calls == 1
    assert first.provenance is not None
    assert "idempotency_key_sha256" in first.provenance.metadata


@pytest.mark.asyncio
async def test_runtime_idempotency_coalesces_concurrent_requests():
    runtime = AgentRuntime()
    agent = BlockingAgent()
    runtime.register(agent)

    first_task = asyncio.create_task(
        runtime.execute("blocking", "shared work", idempotency_key="shared-key")
    )
    await agent.started.wait()
    second_task = asyncio.create_task(
        runtime.execute("blocking", "shared work", idempotency_key="shared-key")
    )
    await asyncio.sleep(0)

    assert agent.calls == 1
    agent.release.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first is second
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_runtime_idempotency_rejects_key_reuse_for_different_payload():
    runtime = AgentRuntime()
    agent = CountingAgent()
    runtime.register(agent)

    await runtime.execute("counting", "first payload", idempotency_key="stable-key")
    with pytest.raises(ValueError, match="different execution payload"):
        await runtime.execute("counting", "second payload", idempotency_key="stable-key")
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_runtime_rejects_empty_idempotency_key():
    runtime = AgentRuntime()
    runtime.register(EchoAgent())
    with pytest.raises(ValueError, match="idempotency_key"):
        await runtime.execute("echo", "build", idempotency_key="   ")


@pytest.mark.asyncio
async def test_memory_put_search_filter_delete():
    store = InMemoryStore()
    item_id = await store.put({"text": "Jeeves tutor memory", "domain": "learning"})
    assert await store.search("jeeves")
    assert await store.search("jeeves", filters={"domain": "game"}) == []
    await store.delete(item_id)
    assert await store.search("jeeves") == []
