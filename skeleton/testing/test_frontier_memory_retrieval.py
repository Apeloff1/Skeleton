"""Shared backend contracts for canonical memory/retrieval consolidation (#118)."""

from __future__ import annotations

from typing import Any

import pytest

from skeleton.frontier.memory import InMemoryStore
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection
from skeleton.frontier.retrieval_context import MemoryRetriever, normalize_retrieval_hit
from skeleton.memory.frontier_adapter import LegacyMemoryStoreAdapter
from skeleton.memory.rag import InMemoryTFIDFStore


SOURCE = {
    "source_repository": "Apeloff1/Prood",
    "source_revision": "aa33a5c9cfaf5558df4144b4ffa016055f401a3a",
    "source_path": "backend/services/rag_service.py",
}


def _backends() -> list[Any]:
    return [
        InMemoryStore(),
        CollectionMemoryAdapter(SQLiteCollection()),
        LegacyMemoryStoreAdapter(InMemoryTFIDFStore(), source_tier="rag"),
    ]


@pytest.mark.asyncio
async def test_memory_backends_share_put_filter_search_delete_contract() -> None:
    for backend in _backends():
        await backend.put(
            {
                "id": "alpha-1",
                "content": "alpha memory about retrieval contracts",
                "metadata": {"topic": "alpha", **SOURCE},
            }
        )
        await backend.put(
            {
                "id": "beta-1",
                "content": "beta memory about unrelated material",
                "metadata": {"topic": "beta", **SOURCE},
            }
        )

        hits = await backend.search(
            "alpha retrieval",
            limit=5,
            filters={"topic": "alpha"},
        )
        assert len(hits) == 1
        assert hits[0]["id"] == "alpha-1"
        assert hits[0]["content"] == "alpha memory about retrieval contracts"
        assert hits[0]["metadata"]["topic"] == "alpha"
        assert hits[0]["metadata"]["source_repository"] == "Apeloff1/Prood"
        assert 0.0 < float(hits[0]["relevance"]) <= 1.0

        await backend.delete("alpha-1")
        assert await backend.search(
            "alpha retrieval",
            limit=5,
            filters={"topic": "alpha"},
        ) == []


@pytest.mark.asyncio
async def test_memory_retriever_preserves_source_provenance_across_backends() -> None:
    for backend in _backends():
        await backend.put(
            {
                "id": "source-1",
                "content": "canonical source provenance survives retrieval",
                "metadata": {"topic": "source", **SOURCE},
            }
        )
        hit = (await MemoryRetriever(backend).retrieve("source provenance", limit=1))[0]

        assert hit.item_id == "source-1"
        assert hit.source_repository == SOURCE["source_repository"]
        assert hit.source_revision == SOURCE["source_revision"]
        assert hit.source_path == SOURCE["source_path"]
        assert hit.audit_summary()["content_sha256"]
        assert "content" not in hit.audit_summary()


def test_runtime_retrieval_rejects_unattributed_memory() -> None:
    with pytest.raises(ValueError, match="source_repository"):
        normalize_retrieval_hit(
            {
                "id": "orphan",
                "content": "unattributed context",
                "metadata": {},
                "relevance": 1.0,
            }
        )


@pytest.mark.asyncio
async def test_legacy_adapter_rejects_nonportable_metadata_before_store_mutation() -> None:
    adapter = LegacyMemoryStoreAdapter(InMemoryTFIDFStore(), source_tier="rag")

    with pytest.raises(TypeError, match="JSON-compatible"):
        await adapter.put(
            {
                "id": "bad",
                "content": "bad metadata",
                "metadata": {"bad": object()},
            }
        )

    assert await adapter.search("bad", limit=5) == []
