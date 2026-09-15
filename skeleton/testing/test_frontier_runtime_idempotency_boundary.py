from __future__ import annotations

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime


class BoundaryAgent:
    name = "runtime-idempotency-boundary"
    capabilities = {"text.generate"}

    def __init__(self) -> None:
        self.calls = 0

    async def run(self, task, context=None):
        self.calls += 1
        return {"task": task, "context": dict(context or {})}


class FatalSignal(BaseException):
    pass


class OneShotFatalAgent(BoundaryAgent):
    name = "runtime-idempotency-fatal"

    async def run(self, task, context=None):
        self.calls += 1
        if self.calls == 1:
            raise FatalSignal("synthetic fatal boundary")
        return {"task": task, "context": dict(context or {})}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("context", "error_type", "message"),
    [
        ({"value": object()}, TypeError, "JSON-compatible values"),
        ({"value": float("nan")}, ValueError, "finite JSON numbers"),
        ({1: "numeric-key"}, TypeError, "JSON object keys must be strings"),
        ({"value": (1, 2)}, TypeError, "JSON-compatible values"),
    ],
    ids=[
        "opaque-object",
        "nan",
        "non-string-key",
        "tuple-is-not-json-array",
    ],
)
async def test_keyed_execution_rejects_noncanonical_context_before_agent_side_effects(
    context,
    error_type,
    message: str,
):
    runtime = AgentRuntime()
    agent = BoundaryAgent()
    runtime.register(agent)

    with pytest.raises(error_type, match=message):
        await runtime.execute(
            agent.name,
            "deterministic task",
            context=context,
            idempotency_key="request-1",
        )

    assert agent.calls == 0


@pytest.mark.asyncio
async def test_keyed_execution_rejects_recursive_context_before_reservation():
    runtime = AgentRuntime()
    agent = BoundaryAgent()
    runtime.register(agent)
    recursive: list[object] = []
    recursive.append(recursive)

    with pytest.raises(ValueError, match="recursive containers"):
        await runtime.execute(
            agent.name,
            "deterministic task",
            context={"recursive": recursive},
            idempotency_key="request-recursive",
        )

    assert agent.calls == 0


@pytest.mark.asyncio
async def test_idempotency_key_is_an_exact_identity_boundary():
    runtime = AgentRuntime()
    agent = BoundaryAgent()
    runtime.register(agent)

    with pytest.raises(ValueError, match="idempotency_key must be normalized"):
        await runtime.execute(
            agent.name,
            "deterministic task",
            idempotency_key=" request-1 ",
        )

    assert agent.calls == 0


@pytest.mark.asyncio
async def test_equivalent_json_context_order_reuses_one_execution():
    runtime = AgentRuntime()
    agent = BoundaryAgent()
    runtime.register(agent)

    first = await runtime.execute(
        agent.name,
        "deterministic task",
        context={"outer": {"b": 2, "a": 1}, "items": [1, 2]},
        idempotency_key="request-order",
    )
    second = await runtime.execute(
        agent.name,
        "deterministic task",
        context={"items": [1, 2], "outer": {"a": 1, "b": 2}},
        idempotency_key="request-order",
    )

    assert first is second
    assert first.succeeded
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_unkeyed_execution_keeps_provider_neutral_python_context_behavior():
    runtime = AgentRuntime()
    agent = BoundaryAgent()
    runtime.register(agent)
    marker = object()

    result = await runtime.execute(
        agent.name,
        "unkeyed task",
        context={"marker": marker},
    )

    assert result.succeeded
    assert result.output["context"]["marker"] is marker
    assert agent.calls == 1


@pytest.mark.asyncio
async def test_fatal_owner_failure_releases_idempotency_reservation_for_retry():
    runtime = AgentRuntime()
    agent = OneShotFatalAgent()
    runtime.register(agent)

    with pytest.raises(FatalSignal, match="synthetic fatal boundary"):
        await runtime.execute(
            agent.name,
            "retryable task",
            context={"attempt": 1},
            idempotency_key="retry-after-fatal",
        )

    retried = await runtime.execute(
        agent.name,
        "retryable task",
        context={"attempt": 1},
        idempotency_key="retry-after-fatal",
    )

    assert retried.succeeded
    assert agent.calls == 2
