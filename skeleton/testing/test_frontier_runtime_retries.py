import asyncio

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.execution import ExecutionPolicy, ExecutionStatus, TransientAgentError


class FlakyAgent:
    name = "flaky"
    capabilities = set()

    def __init__(self, failure=TransientAgentError):
        self.calls = 0
        self.failure = failure
        self.seen = []

    async def run(self, task, context=None):
        self.calls += 1
        self.seen.append(list(context["values"]))
        context["values"].append(self.calls)
        if self.calls < 3:
            raise self.failure("secret upstream detail")
        return self.calls


@pytest.mark.asyncio
async def test_explicit_transient_retries_are_bounded_and_context_is_fresh():
    agent = FlakyAgent()
    runtime = AgentRuntime({agent.name: agent}, execution_policy=ExecutionPolicy(max_attempts=3, retry_delay=0.001))
    result = await runtime.execute(agent.name, "work", context={"values": []})
    assert result.succeeded and result.attempts == 3
    assert agent.seen == [[], [], []]
    assert runtime.stats()["retries"] == 2


@pytest.mark.asyncio
async def test_unknown_failures_are_not_retried_or_exposed():
    agent = FlakyAgent(ValueError)
    runtime = AgentRuntime({agent.name: agent}, execution_policy=ExecutionPolicy(max_attempts=3))
    result = await runtime.execute(agent.name, "work", context={"values": []})
    assert result.status is ExecutionStatus.FAILED
    assert result.attempts == 1
    assert "secret" not in result.error


@pytest.mark.asyncio
async def test_total_deadline_covers_retry_backoff():
    agent = FlakyAgent()
    runtime = AgentRuntime({agent.name: agent}, execution_policy=ExecutionPolicy(
        max_attempts=3, execution_timeout=0.01, retry_delay=0.1))
    result = await runtime.execute(agent.name, "work", context={"values": []})
    assert result.status is ExecutionStatus.TIMED_OUT
    assert agent.calls == 1
    assert runtime.stats()["active"] == 0


@pytest.mark.asyncio
async def test_provider_timeout_is_a_failure_without_claiming_runtime_expiry():
    agent = FlakyAgent(TimeoutError)
    runtime = AgentRuntime({agent.name: agent})
    assert (await runtime.execute(agent.name, "work", context={"values": []})).status is ExecutionStatus.FAILED
