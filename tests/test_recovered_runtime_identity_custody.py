"""Replay custody and identifier budget regressions."""
import asyncio

import pytest

from backend.core.core_v1.keys import KeyProviderError, parse_keyring
from skeleton.ai.model_runtime.native_fair_stream_backend import (
    NativeFairStreamDenied, NativePromptRegistry,
)
from skeleton.frontier.runtime.agent_runtime import AgentRuntime
from skeleton.frontier.runtime.memory_adapters import SQLiteCollection


class Agent:
    name = "echo"
    capabilities = set()

    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, task, context=None):
        self.entered.set()
        await self.release.wait()
        return context


@pytest.mark.asyncio
async def test_replay_output_and_provenance_are_detached():
    agent = Agent()
    runtime = AgentRuntime({"echo": agent})
    agent.release.set()
    first = await runtime.execute("echo", "run", context={"nested": [1]}, idempotency_key="key")
    first.output["nested"].append(2)
    first.provenance.metadata["agent"] = "changed"
    again = await runtime.execute("echo", "run", context={"nested": [1]}, idempotency_key="key")
    assert again.output == {"nested": [1]}
    assert again.provenance.metadata["agent"] == "echo"


@pytest.mark.asyncio
async def test_waiter_capacity_and_nonidempotent_context():
    agent = Agent()
    runtime = AgentRuntime({"echo": agent}, max_idempotency_waiters=1)
    with pytest.raises(ValueError):
        await runtime.execute("echo", "run", context={"x": float("nan")})
    owner = asyncio.create_task(runtime.execute("echo", "run", idempotency_key="key"))
    await agent.entered.wait()
    waiter = asyncio.create_task(runtime.execute("echo", "run", idempotency_key="key"))
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="waiter capacity"):
        await runtime.execute("echo", "run", idempotency_key="key")
    agent.release.set()
    assert (await owner).succeeded and (await waiter).succeeded


def test_memory_duplicate_batch_is_rejected_atomically():
    with SQLiteCollection() as store:
        with pytest.raises(ValueError, match="duplicate"):
            store.add(ids=["same", "same"], documents=["x", "y"], metadatas=[{}, {}])
        assert store.count() == 0
        with pytest.raises(ValueError):
            store.delete(ids=["x" * 257])


def test_malformed_key_identifier_does_not_echo_input():
    invalid = "PRIVATE-INVALID-KEY-IDENTIFIER!" * 2
    with pytest.raises(KeyProviderError) as exc:
        parse_keyring(invalid + ":?")
    assert invalid not in str(exc.value)


def test_revocation_does_not_expand_identity_capacity(monkeypatch):
    from skeleton.ai.model_runtime import native_fair_stream_backend as native

    monkeypatch.setattr(native, "MAX_PROMPT_IDENTITIES", 32)
    registry = NativePromptRegistry(session_id="session")
    for index in range(32):
        registry.revoke(f"request-{index}")
    with pytest.raises(NativeFairStreamDenied, match="capacity"):
        registry.revoke("overflow")
    assert registry.status()["consumed_or_revoked"] == 32
