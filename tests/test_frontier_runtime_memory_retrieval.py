"""Regression coverage for canonical memory retrieval in AgentRuntime."""

from __future__ import annotations

import asyncio

import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.memory import InMemoryStore


class _RecordingAgent:
    name = "memory-agent"
    capabilities = {"research"}

    def __init__(self) -> None:
        self.calls = 0
        self.context = None

    async def run(self, task, context=None):
        self.calls += 1
        self.context = context
        return {
            "task": task,
            "retrieved": len((context or {}).get("retrieved_context", [])),
        }


def test_runtime_uses_memory_contract_and_preserves_source_provenance() -> None:
    async def scenario() -> None:
        memory = InMemoryStore()
        await memory.put(
            {
                "id": "m1",
                "content": "alpha memory",
                "metadata": {
                    "topic": "alpha",
                    "source_repository": "Apeloff1/Prood",
                    "source_revision": "abc123",
                    "source_path": "backend/services/rag_service.py",
                },
            }
        )

        agent = _RecordingAgent()
        runtime = AgentRuntime(memory=memory)
        runtime.register(agent)

        result = await runtime.execute(
            "memory-agent",
            "answer from memory",
            memory_query="alpha",
            memory_limit=2,
            memory_filters={"topic": "alpha"},
        )

        assert result.succeeded
        assert result.output == {"task": "answer from memory", "retrieved": 1}
        assert agent.calls == 1
        assert agent.context is not None
        assert agent.context["retrieved_context"] == [
            {
                "id": "m1",
                "content": "alpha memory",
                "metadata": {
                    "topic": "alpha",
                    "source_repository": "Apeloff1/Prood",
                    "source_revision": "abc123",
                    "source_path": "backend/services/rag_service.py",
                },
                "source": {
                    "repository": "Apeloff1/Prood",
                    "revision": "abc123",
                    "path": "backend/services/rag_service.py",
                },
                "relevance": 1.0,
            }
        ]

        assert result.provenance is not None
        metadata = result.provenance.metadata
        assert metadata["retrieval_request"] == {
            "query_sha256": stable_content_digest("alpha"),
            "limit": 2,
            "filters_sha256": stable_content_digest({"topic": "alpha"}),
        }
        assert metadata["retrieval_hits"] == [
            {
                "id": "m1",
                "content_sha256": stable_content_digest("alpha memory"),
                "source_repository": "Apeloff1/Prood",
                "source_revision": "abc123",
                "source_path": "backend/services/rag_service.py",
                "relevance": 1.0,
            }
        ]
        assert "content" not in metadata["retrieval_hits"][0]

    asyncio.run(scenario())


def test_runtime_retrieval_fails_closed_without_source_provenance() -> None:
    async def scenario() -> None:
        memory = InMemoryStore()
        await memory.put(
            {
                "id": "m1",
                "content": "alpha memory",
                "metadata": {"topic": "alpha"},
            }
        )

        agent = _RecordingAgent()
        runtime = AgentRuntime(memory=memory)
        runtime.register(agent)

        result = await runtime.execute(
            "memory-agent",
            "answer from memory",
            memory_query="alpha",
        )

        assert not result.succeeded
        assert result.error is not None
        assert "source_repository" in result.error
        assert agent.calls == 0
        assert result.provenance is not None
        assert result.provenance.metadata["retrieval_request"]["query_sha256"] == stable_content_digest("alpha")
        assert "retrieval_hits" not in result.provenance.metadata

    asyncio.run(scenario())


def test_retrieval_request_is_part_of_idempotency_identity() -> None:
    async def scenario() -> None:
        memory = InMemoryStore()
        for item_id, content in (("m1", "alpha memory"), ("m2", "beta memory")):
            await memory.put(
                {
                    "id": item_id,
                    "content": content,
                    "metadata": {"source_repository": "Apeloff1/Prood"},
                }
            )

        agent = _RecordingAgent()
        runtime = AgentRuntime(memory=memory)
        runtime.register(agent)

        first = await runtime.execute(
            "memory-agent",
            "answer",
            memory_query="alpha",
            idempotency_key="same-key",
        )
        assert first.succeeded

        with pytest.raises(ValueError, match="idempotency key reused"):
            await runtime.execute(
                "memory-agent",
                "answer",
                memory_query="beta",
                idempotency_key="same-key",
            )

        assert agent.calls == 1

    asyncio.run(scenario())


def test_runtime_returns_failure_when_retrieval_is_requested_without_memory() -> None:
    async def scenario() -> None:
        agent = _RecordingAgent()
        runtime = AgentRuntime()
        runtime.register(agent)

        result = await runtime.execute(
            "memory-agent",
            "answer",
            memory_query="alpha",
        )

        assert not result.succeeded
        assert result.error is not None
        assert "configured canonical MemoryContract" in result.error
        assert agent.calls == 0

    asyncio.run(scenario())
