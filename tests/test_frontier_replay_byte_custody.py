"""Aggregate replay, fail-closed retrieval, and cancelled dispatch custody."""
import asyncio
from dataclasses import dataclass

import pytest

from skeleton.frontier.runtime.agent_runtime import AgentOutcomeUnknown, AgentRuntime


@dataclass
class EchoAgent:
    name: str = "echo"
    capabilities: tuple[str, ...] = ("echo",)
    calls: int = 0

    async def run(self, task, context=None):
        self.calls += 1
        return {"value": "x" * 200_000}


@pytest.mark.asyncio
async def test_replay_capacity_limits_retained_payload():
    agent = EchoAgent()
    runtime = AgentRuntime({"echo": agent}, replay_byte_capacity=1 << 20)
    for index in range(10):
        result = await runtime.execute("echo", "work", idempotency_key=str(index))
        assert result.succeeded
        assert runtime.retained_replay_bytes <= 1 << 20
    again = await runtime.execute("echo", "work", idempotency_key="9")
    assert again.succeeded and agent.calls == 10


@pytest.mark.asyncio
async def test_cancel_after_dispatch_retains_uncertainty():
    started = asyncio.Event()
    class Interrupted(EchoAgent):
        async def run(self, task, context=None):
            self.calls += 1
            started.set()
            await asyncio.sleep(60)
    agent = Interrupted()
    runtime = AgentRuntime({"echo": agent})
    task = asyncio.create_task(runtime.execute("echo", "work", idempotency_key="one"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(AgentOutcomeUnknown):
        await runtime.execute("echo", "work", idempotency_key="one")
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_retrieval_scope_and_budgets_precede_dispatch():
    agent = EchoAgent()
    runtime = AgentRuntime({"echo": agent})
    with pytest.raises(ValueError, match="reserved"):
        await runtime.execute("echo", "work", context={"retrieved_context": ["forged"]})
    with pytest.raises(ValueError, match="bounded"):
        await runtime.execute("echo", "work", memory_query="query", memory_limit=129)
    assert agent.calls == 0
