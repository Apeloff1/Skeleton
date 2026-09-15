from __future__ import annotations

import pytest

from skeleton.frontier.memory import InMemoryStore
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection


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
    assert len(await store.search("frontier")) == 2
    assert len(await store.search("learning", filters={"domain": "learning"})) == 1
    assert len(await store.search("context", filters={"user_id": "u1"})) == 1
    assert await store.search("learning", filters={"domain": "game"}) == []
    assert await store.search("frontier", limit=0) == []

    await store.delete(first_id)
    assert await store.search("learning", filters={"user_id": "u1"}) == []
    assert len(await store.search("frontier")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
async def test_memory_contract_conformance_across_reference_and_sqlite(
    backend: str,
    tmp_path,
):
    if backend == "reference":
        await _exercise_memory_contract(InMemoryStore())
        return

    collection = SQLiteCollection(tmp_path / "frontier.sqlite3")
    try:
        await _exercise_memory_contract(CollectionMemoryAdapter(collection))
    finally:
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


@pytest.mark.asyncio
async def test_sqlite_collection_ranks_lexical_matches_and_filters_metadata(tmp_path):
    collection = SQLiteCollection(tmp_path / "ranking.sqlite3")
    adapter = CollectionMemoryAdapter(collection)
    try:
        await adapter.put(
            {
                "id": "partial",
                "text": "frontier memory adapter",
                "domain": "learning",
            }
        )
        await adapter.put(
            {
                "id": "exact",
                "text": "frontier runtime contract",
                "domain": "runtime",
            }
        )
        await adapter.put(
            {
                "id": "irrelevant",
                "text": "ocean weather simulation",
                "domain": "world",
            }
        )

        hits = await adapter.search("frontier runtime", limit=3)
        assert [hit["id"] for hit in hits] == ["exact", "partial"]
        assert hits[0]["relevance"] == pytest.approx(1.0)
        assert hits[1]["relevance"] == pytest.approx(0.5)
        assert await adapter.search(
            "frontier runtime",
            filters={"domain": "world"},
        ) == []
    finally:
        collection.close()


@pytest.mark.asyncio
async def test_collection_adapter_rejects_conflicting_filter_fields(tmp_path):
    collection = SQLiteCollection(tmp_path / "conflict.sqlite3")
    try:
        adapter = CollectionMemoryAdapter(collection)
        with pytest.raises(ValueError, match="conflicting memory metadata field: domain"):
            await adapter.put(
                {
                    "id": "bad",
                    "text": "conflicting item",
                    "domain": "learning",
                    "metadata": {"domain": "game"},
                }
            )
        assert collection.count() == 0
    finally:
        collection.close()
