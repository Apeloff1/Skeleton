import pytest

from skeleton.frontier.agent_runtime import AgentRuntime
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter
from skeleton.frontier.npc_adapters import npc_spec_from_domain_record


class FakeCollection:
    def __init__(self):
        self.documents = []

    def add(self, *, documents, metadatas, ids):
        for document, metadata, item_id in zip(documents, metadatas, ids):
            self.documents.append(
                {"id": item_id, "document": document, "metadata": dict(metadata)}
            )

    def query(self, *, query_texts, n_results, where=None):
        matches = self.documents
        if where:
            matches = [
                item
                for item in matches
                if all(item["metadata"].get(key) == value for key, value in where.items())
            ]
        matches = matches[-n_results:]
        return {
            "documents": [[item["document"] for item in matches]],
            "metadatas": [[item["metadata"] for item in matches]],
            "ids": [[item["id"] for item in matches]],
            "distances": [[0.1 for _ in matches]],
        }

    def delete(self, *, ids=None, where=None):
        if ids:
            self.documents = [item for item in self.documents if item["id"] not in ids]


class MultiCapabilityAgent:
    name = "integrator"
    capabilities = {"memory.search", "npc.normalize", "provenance.emit"}

    async def run(self, task, context=None):
        return {"task": task, "context": dict(context or {}), "status": "ok"}


def test_stable_content_digest_canonicalizes_mapping_order():
    left = {"b": 2, "a": {"y": 2, "x": 1}}
    right = {"a": {"x": 1, "y": 2}, "b": 2}

    assert stable_content_digest(left) == stable_content_digest(right)
    assert len(stable_content_digest(left)) == 64


@pytest.mark.asyncio
async def test_collection_memory_adapter_preserves_rag_semantics():
    collection = FakeCollection()
    adapter = CollectionMemoryAdapter(collection)

    item_id = await adapter.put(
        {
            "id": "session-1",
            "content": "Jeeves remembers the frontier integration wave",
            "metadata": {"user_id": "u1", "topic": "frontier"},
        }
    )

    assert item_id == "session-1"
    hits = await adapter.search(
        "frontier",
        limit=3,
        filters={"user_id": "u1"},
    )
    assert hits == [
        {
            "content": "Jeeves remembers the frontier integration wave",
            "id": "session-1",
            "metadata": {"user_id": "u1", "topic": "frontier"},
            "relevance": pytest.approx(0.9),
        }
    ]

    await adapter.delete("session-1")
    assert await adapter.search("frontier") == []


def test_domain_npc_adapter_preserves_unique_lore_without_new_npc_hierarchy():
    source = {
        "id": "barnacle_bill",
        "name": "Barnacle Bill",
        "title": "Legendary Fisherman",
        "role": "mentor",
        "personality": "wise_gruff",
        "description": "An ancient fisherman who has seen every sea.",
        "faction": "fishermen_guild",
        "initial_disposition": 50,
        "voice_style": "gruff_but_kind",
        "schedule": {"morning": "docks", "evening": "tavern"},
        "skills_taught": ["basic_fishing", "weather_reading"],
        "quests_offered": ["first_catch"],
    }

    npc = npc_spec_from_domain_record(source)

    assert npc.name == "Barnacle Bill"
    assert npc.archetype == "mentor"
    assert "wise_gruff" in npc.traits
    assert npc.stats["disposition"] == 50
    assert "faction:fishermen_guild" in npc.tags
    assert npc.metadata["id"] == "barnacle_bill"
    assert npc.metadata["schedule"]["morning"] == "docks"
    assert npc.metadata["quests_offered"] == ["first_catch"]


@pytest.mark.asyncio
async def test_runtime_requires_capability_set_and_emits_source_bound_digest():
    runtime = AgentRuntime()
    runtime.register(MultiCapabilityAgent())

    result = await runtime.execute(
        "integrator",
        "normalize promoted candidate",
        context={"wave": 2},
        required_capabilities={"memory.search", "npc.normalize"},
        source_repository="Apeloff1/Prood",
        source_revision="b67167f1135744e74827ce03b0bf5d766e800cf4",
        source_path="backend/services/rag_service.py",
    )

    assert result.succeeded
    assert result.provenance is not None
    assert result.provenance.source_repository == "Apeloff1/Prood"
    assert result.provenance.source_path == "backend/services/rag_service.py"
    assert result.provenance.content_sha256 == stable_content_digest(result.output)
    assert result.provenance.metadata["required_capabilities"] == [
        "memory.search",
        "npc.normalize",
    ]


@pytest.mark.asyncio
async def test_runtime_rejects_when_any_required_capability_is_missing():
    runtime = AgentRuntime()
    runtime.register(MultiCapabilityAgent())

    with pytest.raises(PermissionError, match="world.simulate"):
        await runtime.execute(
            "integrator",
            "promote",
            required_capabilities={"memory.search", "world.simulate"},
        )
