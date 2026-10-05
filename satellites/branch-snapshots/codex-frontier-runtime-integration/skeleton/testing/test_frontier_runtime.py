import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.capabilities import CapabilityPolicy
from skeleton.frontier.health import HealthState
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


@pytest.mark.asyncio
async def test_runtime_executes_with_capability_gate_and_provenance():
    runtime = AgentRuntime(policy=CapabilityPolicy.from_names({"text.generate"}))
    runtime.register(EchoAgent())
    result = await runtime.execute(
        "echo", "build npc", context={"world": "frontier"}, required_capability="text.generate"
    )
    assert result.succeeded
    assert result.output["task"] == "build npc"
    assert result.provenance is not None
    assert result.provenance.operation == "agent.execute.completed"


@pytest.mark.asyncio
async def test_runtime_rejects_missing_agent_capability():
    runtime = AgentRuntime(policy=CapabilityPolicy.from_names({"code.execute"}))
    runtime.register(EchoAgent())
    with pytest.raises(PermissionError, match="lacks capability"):
        await runtime.execute("echo", "build", required_capability="code.execute")


@pytest.mark.asyncio
async def test_runtime_rejects_capability_not_allowed_by_policy():
    runtime = AgentRuntime(policy=CapabilityPolicy.from_names({"code.execute"}))
    runtime.register(EchoAgent())
    with pytest.raises(PermissionError, match="missing capabilities"):
        await runtime.execute("echo", "build", required_capability="text.generate")


@pytest.mark.asyncio
async def test_runtime_rejects_when_unavailable():
    runtime = AgentRuntime(
        policy=CapabilityPolicy.from_names({"text.generate"}),
        health=HealthState.UNAVAILABLE,
    )
    runtime.register(EchoAgent())
    with pytest.raises(RuntimeError, match="unavailable"):
        await runtime.execute("echo", "build")


@pytest.mark.asyncio
async def test_runtime_contains_failures_as_results():
    runtime = AgentRuntime(policy=CapabilityPolicy.from_names({"text.generate"}))
    runtime.register(BrokenAgent())
    result = await runtime.execute("broken", "fail safely")
    assert not result.succeeded
    assert "RuntimeError" in result.error


@pytest.mark.asyncio
async def test_memory_put_search_filter_delete():
    store = InMemoryStore()
    item_id = await store.put({"text": "Jeeves tutor memory", "domain": "learning"})
    assert await store.search("jeeves")
    assert await store.search("jeeves", filters={"domain": "game"}) == []
    await store.delete(item_id)
    assert await store.search("jeeves") == []
