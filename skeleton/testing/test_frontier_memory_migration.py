"""Contract tests for migrating legacy memory stores behind Frontier retrieval."""

from __future__ import annotations

import asyncio
from typing import Any

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.memory.frontier_adapter import LegacyMemoryStoreAdapter
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk, MemoryQueryResult


class _LegacyStore(MemoryStore):
    def __init__(self) -> None:
        self.chunks: dict[str, MemoryChunk] = {}

    def add(self, chunk: MemoryChunk) -> None:
        self.chunks[chunk.id] = chunk

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: dict[str, Any] | None = None,
        min_score: float = 0.0,
    ) -> list[MemoryQueryResult]:
        del query_text
        results: list[MemoryQueryResult] = []
        for chunk in self.chunks.values():
            if metadata_filter and any(
                chunk.metadata.get(key) != value
                for key, value in metadata_filter.items()
            ):
                continue
            score = 1.0
            if score < min_score:
                continue
            results.append(
                MemoryQueryResult(
                    chunk=chunk,
                    score=score,
                    rank=len(results) + 1,
                )
            )
            if len(results) >= top_k:
                break
        return results

    def delete(self, chunk_id: str) -> bool:
        return self.chunks.pop(chunk_id, None) is not None

    def health(self) -> dict[str, Any]:
        return {"status": "ok", "count": len(self.chunks)}


class _RecordingAgent:
    name = "legacy-memory-agent"
    capabilities = {"research"}

    def __init__(self) -> None:
        self.context: dict[str, Any] | None = None

    async def run(self, task: str, context=None):
        del task
        self.context = dict(context or {})
        return self.context.get("retrieved_context", [])


def test_legacy_adapter_supplies_explicit_source_provenance() -> None:
    async def scenario() -> None:
        store = _LegacyStore()
        adapter = LegacyMemoryStoreAdapter(
            store,
            source_repository="Apeloff1/LegacyMemory",
            source_revision="deadbeef",
            source_path="skeleton/memory",
            source_tier="rag",
        )

        item_id = await adapter.put(
            {
                "id": "legacy-1",
                "content": "legacy alpha memory",
                "metadata": {"topic": "alpha"},
            }
        )
        assert item_id == "legacy-1"
        assert store.chunks[item_id].metadata == {
            "topic": "alpha",
            "source_repository": "Apeloff1/LegacyMemory",
            "source_revision": "deadbeef",
            "source_path": "skeleton/memory",
        }

        hits = await adapter.search(
            "alpha",
            limit=1,
            filters={"topic": "alpha"},
        )
        assert hits == [
            {
                "id": "legacy-1",
                "content": "legacy alpha memory",
                "metadata": {
                    "topic": "alpha",
                    "source_repository": "Apeloff1/LegacyMemory",
                    "source_revision": "deadbeef",
                    "source_path": "skeleton/memory",
                    "source_tier": "rag",
                },
                "relevance": 1.0,
            }
        ]

    asyncio.run(scenario())


def test_legacy_store_reaches_agent_through_canonical_memory_boundary() -> None:
    async def scenario() -> None:
        store = _LegacyStore()
        adapter = LegacyMemoryStoreAdapter(
            store,
            source_repository="Apeloff1/LegacyMemory",
            source_tier="rag",
        )
        await adapter.put(
            {
                "id": "legacy-1",
                "content": "legacy alpha memory",
                "metadata": {"topic": "alpha"},
            }
        )

        agent = _RecordingAgent()
        runtime = AgentRuntime(memory=adapter)
        runtime.register(agent)

        result = await runtime.execute(
            agent.name,
            "answer",
            memory_query="alpha",
            memory_filters={"topic": "alpha"},
        )

        assert result.succeeded
        assert agent.context is not None
        hit = agent.context["retrieved_context"][0]
        assert hit["source"]["repository"] == "Apeloff1/LegacyMemory"
        assert result.provenance is not None
        assert result.provenance.metadata["retrieval_hits"][0]["source_repository"] == "Apeloff1/LegacyMemory"

    asyncio.run(scenario())