from __future__ import annotations

import pytest

from skeleton.frontier.memory import InMemoryStore
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection


def _backend_store(backend: str, tmp_path, name: str):
    if backend == "reference":
        return InMemoryStore(), None
    collection = SQLiteCollection(tmp_path / f"{name}.sqlite3")
    return CollectionMemoryAdapter(collection), collection


async def _exercise_memory_contract(store) -> None:
    first_id = await store.put(
        {
            "id": "learning-1",
            "text": "frontier memory preserves learning context",
            "domain": "learning",
            "metadata": {"user_id": "u1"},
        }
    )
    second_id = await store.put(
        {
            "id": "game-1",
            "text": "frontier NPC memory preserves world context",
            "domain": "game",
            "metadata": {"user_id": "u2"},
        }
    )

    assert first_id == "learning-1"
    assert second_id == "game-1"

    frontier_hits = await store.search("frontier")
    assert {hit["id"] for hit in frontier_hits} == {"learning-1", "game-1"}
    for hit in frontier_hits:
        assert set(hit) == {"id", "content", "metadata", "relevance"}
        assert hit["metadata"]["domain"] in {"learning", "game"}
        assert 0.0 <= hit["relevance"] <= 1.0

    learning_hits = await store.search("learning", filters={"domain": "learning"})
    assert [hit["id"] for hit in learning_hits] == ["learning-1"]
    assert len(await store.search("context", filters={"user_id": "u1"})) == 1
    assert await store.search("learning", filters={"domain": "game"}) == []
    assert await store.search("frontier", limit=0) == []

    upsert_id = await store.put(
        {
            "id": "game-1",
            "document": "updated frontier world memory",
            "domain": "world",
            "metadata": {"user_id": "u3"},
        }
    )
    assert upsert_id == "game-1"
    assert await store.search("NPC") == []
    updated = await store.search(
        "updated frontier",
        filters={"domain": "world", "user_id": "u3"},
    )
    assert [hit["id"] for hit in updated] == ["game-1"]
    assert updated[0]["content"] == "updated frontier world memory"
    assert updated[0]["metadata"] == {"domain": "world", "user_id": "u3"}
    assert await store.search("updated", filters={"domain": "game"}) == []

    await store.delete(first_id)
    assert await store.search("learning", filters={"user_id": "u1"}) == []
    assert [hit["id"] for hit in await store.search("frontier")] == ["game-1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
async def test_memory_contract_conformance_across_reference_and_sqlite(
    backend: str,
    tmp_path,
):
    store, collection = _backend_store(backend, tmp_path, "frontier")
    try:
        await _exercise_memory_contract(store)
    finally:
        if collection is not None:
            collection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
async def test_memory_contract_rejects_invalid_items_consistently(backend: str, tmp_path):
    store, collection = _backend_store(backend, tmp_path, "invalid")
    try:
        with pytest.raises(ValueError, match="memory id must not be empty"):
            await store.put({"id": "   ", "text": "valid content"})

        with pytest.raises(ValueError, match="requires non-empty content/text/document"):
            await store.put({"id": "missing-content", "metadata": {"domain": "learning"}})

        with pytest.raises(TypeError, match="metadata must be a mapping"):
            await store.put(
                {"id": "bad-metadata", "text": "content", "metadata": ["not", "mapping"]}
            )

        with pytest.raises(ValueError, match="conflicting memory metadata field: domain"):
            await store.put(
                {
                    "id": "conflict",
                    "text": "conflicting item",
                    "domain": "learning",
                    "metadata": {"domain": "game"},
                }
            )

        with pytest.raises(ValueError, match="memory id must not be empty"):
            await store.delete("   ")
    finally:
        if collection is not None:
            assert collection.count() == 0
            collection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
async def test_memory_contract_shares_lexical_ranking_and_filters(backend: str, tmp_path):
    store, collection = _backend_store(backend, tmp_path, "ranking")
    try:
        await store.put(
            {
                "id": "partial",
                "text": "frontier memory adapter",
                "domain": "learning",
            }
        )
        await store.put(
            {
                "id": "exact",
                "text": "frontier runtime contract",
                "domain": "runtime",
            }
        )
        await store.put(
            {
                "id": "irrelevant",
                "text": "ocean weather simulation",
                "domain": "world",
            }
        )

        hits = await store.search("frontier runtime", limit=3)
        assert [hit["id"] for hit in hits] == ["exact", "partial"]
        assert hits[0]["relevance"] == pytest.approx(1.0)
        assert hits[1]["relevance"] == pytest.approx(0.5)
        assert await store.search(
            "frontier runtime",
            filters={"domain": "world"},
        ) == []
    finally:
        if collection is not None:
            collection.close()


@pytest.mark.asyncio
async def test_sqlite_collection_persists_across_reopen(tmp_path):
    database = tmp_path / "persistent-memory.sqlite3"

    first = SQLiteCollection(database, namespace="learning")
    try:
        adapter = CollectionMemoryAdapter(first)
        await adapter.put(
            {
                "id": "session-42",
                "content": "persistent frontier session",
                "domain": "learning",
                "metadata": {"user_id": "u42"},
            }
        )
        assert first.count() == 1
    finally:
        first.close()

    second = SQLiteCollection(database, namespace="learning")
    try:
        adapter = CollectionMemoryAdapter(second)
        hits = await adapter.search(
            "persistent frontier",
            filters={"user_id": "u42", "domain": "learning"},
        )
        assert [hit["id"] for hit in hits] == ["session-42"]
        assert hits[0]["relevance"] == pytest.approx(1.0)
    finally:
        second.close()


@pytest.mark.asyncio
async def test_sqlite_collection_isolates_namespaces(tmp_path):
    database = tmp_path / "namespaces.sqlite3"
    learning = SQLiteCollection(database, namespace="learning")
    game = SQLiteCollection(database, namespace="game")
    try:
        await CollectionMemoryAdapter(learning).put(
            {"id": "same-id", "text": "learning memory", "domain": "learning"}
        )
        await CollectionMemoryAdapter(game).put(
            {"id": "same-id", "text": "game memory", "domain": "game"}
        )

        assert learning.count() == 1
        assert game.count() == 1
        learning_hits = await CollectionMemoryAdapter(learning).search("learning")
        game_hits = await CollectionMemoryAdapter(game).search("game")
        assert learning_hits[0]["content"] == "learning memory"
        assert game_hits[0]["content"] == "game memory"
    finally:
        learning.close()
        game.close()
