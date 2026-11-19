"""Identity admission at the maintained AgentRuntime boundary."""
import asyncio

import pytest

from skeleton.frontier.runtime.agent_runtime import AgentRuntime


class Echo:
    name = "echo"
    capabilities = set()

    def __init__(self):
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, task, context=None):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return context


@pytest.mark.asyncio
async def test_fingerprinted_context_is_detached_before_execution():
    agent = Echo()
    runtime = AgentRuntime({"echo": agent})
    caller = {"nested": {"value": "original"}}
    task = asyncio.create_task(runtime.execute("echo", "work", context=caller, idempotency_key="one"))
    await agent.entered.wait()
    caller["nested"]["value"] = "mutated"
    agent.release.set()
    result = await task
    assert result.output == {"nested": {"value": "original"}}
    replay = await runtime.execute("echo", "work", context={"nested": {"value": "original"}}, idempotency_key="one")
    assert replay.output == result.output
    assert agent.calls == 1
    with pytest.raises(ValueError, match="idempotency key reused"):
        await runtime.execute("echo", "work", context=caller, idempotency_key="one")


@pytest.mark.asyncio
async def test_oversized_identity_inputs_fail_before_agent_admission():
    agent = Echo()
    runtime = AgentRuntime({"echo": agent})
    nested = []
    for _ in range(70):
        nested = [nested]
    cycle = []
    cycle.append(cycle)
    for payload in (nested, cycle, "x" * 1_048_577, 1 << 4097):
        with pytest.raises(ValueError):
            await runtime.execute("echo", "work", context={"payload": payload}, idempotency_key="one")
    with pytest.raises(ValueError, match="256"):
        await runtime.execute("echo", "work", idempotency_key="x" * 257)
    assert agent.calls == 0
    assert not runtime._idempotent_executions


def test_registry_has_hard_capacity_ceiling():
    with pytest.raises(ValueError):
        AgentRuntime(idempotency_capacity=65_537)
