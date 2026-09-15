from __future__ import annotations

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime


class CountingAgent:
    name = "counting-boundary"
    capabilities = {"text.generate", "memory.write"}

    def __init__(self):
        self.calls = 0

    async def run(self, task, context=None):
        self.calls += 1
        return {"task": task, "context": dict(context or {})}


class BadNameAgent:
    name = " bad-agent "
    capabilities = {"text.generate"}

    async def run(self, task, context=None):
        return task


class BadCapabilitiesAgent:
    name = "bad-capabilities"
    capabilities = "text.generate"

    async def run(self, task, context=None):
        return task


def test_register_rejects_noncanonical_agent_name():
    runtime = AgentRuntime()
    with pytest.raises(ValueError, match="agent name must be normalized"):
        runtime.register(BadNameAgent())


def test_register_rejects_string_capability_container():
    runtime = AgentRuntime()
    with pytest.raises(TypeError, match="iterable of strings, not a string"):
        runtime.register(BadCapabilitiesAgent())


@pytest.mark.parametrize("capacity", [True, 1.5, "4"])
def test_runtime_capacity_requires_real_integer(capacity):
    with pytest.raises(TypeError, match="idempotency_capacity must be an integer"):
        AgentRuntime(idempotency_capacity=capacity)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "error_type", "message"),
    [
        ({"required_capabilities": "text.generate"}, TypeError, "not a string"),
        ({"required_capabilities": {"   "}}, ValueError, "entries must not be empty"),
        ({"required_capability": "   "}, ValueError, "entries must not be empty"),
        ({"context": ["not", "a", "mapping"]}, TypeError, "context must be a mapping"),
        ({"source_repository": "   "}, ValueError, "source_repository must not be empty"),
        ({"source_repository": " repo "}, ValueError, "source_repository must be normalized"),
        ({"source_revision": " rev "}, ValueError, "source_revision must be normalized"),
        ({"source_path": " path "}, ValueError, "source_path must be normalized"),
        ({"idempotency_key": 42}, TypeError, "idempotency_key must be a string"),
    ],
    ids=[
        "capability-string",
        "blank-capability-entry",
        "blank-single-capability",
        "bad-context",
        "empty-source-repo",
        "noncanonical-source-repo",
        "noncanonical-source-revision",
        "noncanonical-source-path",
        "nonstring-idempotency-key",
    ],
)
async def test_invalid_runtime_input_fails_before_agent_side_effects(
    kwargs,
    error_type,
    message: str,
):
    runtime = AgentRuntime()
    agent = CountingAgent()
    runtime.register(agent)

    with pytest.raises(error_type, match=message):
        await runtime.execute("counting-boundary", "valid task", **kwargs)
    assert agent.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_name", "task", "message"),
    [
        (" counting-boundary ", "valid task", "agent name must be normalized"),
        ("counting-boundary", " task ", "task must be normalized"),
        ("counting-boundary", "   ", "task must not be empty"),
    ],
)
async def test_runtime_identity_inputs_must_be_canonical_before_execution(
    agent_name: str,
    task: str,
    message: str,
):
    runtime = AgentRuntime()
    agent = CountingAgent()
    runtime.register(agent)

    with pytest.raises(ValueError, match=message):
        await runtime.execute(agent_name, task)
    assert agent.calls == 0


@pytest.mark.asyncio
async def test_runtime_passes_defensive_context_copy_and_normalized_provenance():
    runtime = AgentRuntime()
    agent = CountingAgent()
    runtime.register(agent)
    context = {"wave": 8}

    result = await runtime.execute(
        "counting-boundary",
        "canonical task",
        context=context,
        required_capabilities={"TEXT.GENERATE", "memory.write"},
        source_repository="Apeloff1/Skeleton",
        source_revision="deadbeef",
        source_path="skeleton/frontier/agent_runtime.py",
    )

    assert result.succeeded
    assert result.output["context"] == {"wave": 8}
    assert result.provenance is not None
    assert result.provenance.metadata["required_capabilities"] == [
        "memory.write",
        "text.generate",
    ]
    context["wave"] = 9
    assert result.output["context"] == {"wave": 8}
