import asyncio

import pytest

from skeleton.frontier.memory import InMemoryStore
from skeleton.frontier.sqlite_memory import SQLiteMemoryStore


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["memory", "sqlite"])
async def test_memory_adapters_share_order_filter_unicode_and_upsert_semantics(tmp_path, kind):
    store = InMemoryStore() if kind == "memory" else SQLiteMemoryStore(tmp_path / "memory.db")
    try:
        await store.put({"id": "b", "text": "Straße", "domain": "game"})
        await store.put({"id": "a", "text": "Straße", "domain": "learning"})
        assert [item["id"] for item in await store.search("STRASSE")] == ["a", "b"]
        assert [item["id"] for item in await store.search("", filters={"domain": "game"})] == ["b"]
        assert len(await store.search("", limit=1)) == 1
        assert await store.search("", limit=0) == []
        await store.put({"id": "a", "text": "replacement"})
        assert [item["id"] for item in await store.search("STRASSE")] == ["b"]
        await store.delete("b")
        assert await store.search("STRASSE") == []
    finally:
        if kind == "sqlite":
            await store.aclose()


@pytest.mark.asyncio
async def test_memory_survives_close_and_reopen_with_original_id(tmp_path):
    path = tmp_path / "memory.db"
    async with SQLiteMemoryStore(path) as store:
        item_id = await store.put({"text": "retained", "nested": [1]})
    async with SQLiteMemoryStore(path) as reopened:
        results = await reopened.search("retained")
        assert results == [{"id": item_id, "text": "retained", "nested": [1]}]
        results[0]["nested"].append(2)
        assert (await reopened.search("retained"))[0]["nested"] == [1]


@pytest.mark.asyncio
async def test_namespaces_isolate_identical_ids_and_deletions(tmp_path):
    path = tmp_path / "memory.db"
    async with SQLiteMemoryStore(path, namespace="one") as one, SQLiteMemoryStore(path, namespace="two") as two:
        await one.put({"id": "same", "text": "one"})
        await two.put({"id": "same", "text": "two"})
        assert await one.search("two") == []
        await one.delete("same")
        assert await one.count() == 0
        assert await two.count() == 1


@pytest.mark.asyncio
async def test_capacity_is_atomic_across_connections_and_failed_write_rolls_back(tmp_path):
    path = tmp_path / "memory.db"
    async with SQLiteMemoryStore(path, capacity=1) as one, SQLiteMemoryStore(path, capacity=1) as two:
        results = await asyncio.gather(one.put({"id": "a"}), two.put({"id": "b"}), return_exceptions=True)
        assert sum(isinstance(result, OverflowError) for result in results) == 1
        assert await one.count() == 1
        existing = (await one.search(""))[0]["id"]
        await two.put({"id": existing, "text": "updated"})
        assert (await one.search("updated"))[0]["id"] == existing


@pytest.mark.asyncio
async def test_invalid_payload_and_sql_like_query_do_not_damage_store(tmp_path):
    async with SQLiteMemoryStore(tmp_path / "memory.db", max_payload_bytes=100) as store:
        with pytest.raises(ValueError):
            await store.put({"text": "x" * 101})
        await store.put({"id": "good", "text": "value"})
        assert await store.search("' OR 1=1 --") == []
        assert await store.count() == 1


@pytest.mark.asyncio
async def test_closed_store_rejects_operations_and_close_is_idempotent(tmp_path):
    store = SQLiteMemoryStore(tmp_path / "memory.db")
    await store.aclose()
    await store.aclose()
    with pytest.raises(RuntimeError, match="closed"):
        await store.search("")
