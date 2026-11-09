from __future__ import annotations

import sqlite3

import pytest

from skeleton.frontier.memory_adapters import (
    CollectionMemoryAdapter,
    MemoryStoreCorruptionError,
    SQLiteCollection,
)


def _rewrite_metadata(database, *, namespace: str, item_id: str, metadata_json: str) -> None:
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE frontier_memory_items
            SET metadata_json = ?
            WHERE namespace = ? AND item_id = ?
            """,
            (metadata_json, namespace, item_id),
        )
        connection.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metadata_json", "message"),
    [
        ('{"score":NaN}', "valid strict JSON"),
        ('{"broken"', "valid strict JSON"),
        ('["not", "an", "object"]', "JSON object"),
        ('{"domain":"a","domain":"b"}', "valid strict JSON"),
    ],
    ids=["non-finite", "malformed", "non-object", "duplicate-key"],
)
async def test_corrupt_sqlite_memory_metadata_never_becomes_a_hit(
    tmp_path,
    metadata_json: str,
    message: str,
):
    database = tmp_path / "memory-corruption.sqlite3"
    namespace = "runtime"
    collection = SQLiteCollection(database, namespace=namespace)
    adapter = CollectionMemoryAdapter(collection)
    try:
        await adapter.put(
            {
                "id": "execution-1",
                "content": "durable runtime outcome",
                "metadata": {"domain": "runtime", "attempt": 1},
            }
        )
        assert collection.count() == 1
    finally:
        collection.close()

    _rewrite_metadata(
        database,
        namespace=namespace,
        item_id="execution-1",
        metadata_json=metadata_json,
    )

    reopened = SQLiteCollection(database, namespace=namespace)
    adapter = CollectionMemoryAdapter(reopened)
    try:
        with pytest.raises(MemoryStoreCorruptionError, match=message):
            await adapter.search("durable runtime")
        assert reopened.count() == 1

        # Exact-id deletion is the explicit repair path and must not require the
        # corrupt metadata to be deserialized first.
        await adapter.delete("execution-1")
        assert reopened.count() == 0
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_exact_get_skips_unrelated_corrupt_rows(tmp_path):
    database = tmp_path / "targeted-get.sqlite3"
    collection = SQLiteCollection(database, namespace="memory")
    adapter = CollectionMemoryAdapter(collection)
    try:
        await adapter.put(
            {"id": "healthy", "content": "healthy memory", "metadata": {"kind": "ok"}}
        )
        await adapter.put(
            {"id": "corrupt", "content": "corrupt memory", "metadata": {"kind": "bad"}}
        )
    finally:
        collection.close()

    _rewrite_metadata(
        database,
        namespace="memory",
        item_id="corrupt",
        metadata_json='{"score":NaN}',
    )

    reopened = SQLiteCollection(database, namespace="memory")
    try:
        healthy = reopened.get(ids=["healthy"])
        assert healthy["ids"] == ["healthy"]
        assert healthy["metadatas"] == [{"kind": "ok"}]

        with pytest.raises(MemoryStoreCorruptionError, match="valid strict JSON"):
            reopened.get()
    finally:
        reopened.close()


def test_filtered_delete_fails_closed_without_partial_mutation(tmp_path):
    database = tmp_path / "filtered-delete.sqlite3"
    collection = SQLiteCollection(database, namespace="memory")
    try:
        collection.add(
            documents=["healthy", "corrupt"],
            metadatas=[{"kind": "target"}, {"kind": "target"}],
            ids=["healthy", "corrupt"],
        )
    finally:
        collection.close()

    _rewrite_metadata(
        database,
        namespace="memory",
        item_id="corrupt",
        metadata_json='{"kind":NaN}',
    )

    reopened = SQLiteCollection(database, namespace="memory")
    try:
        with pytest.raises(MemoryStoreCorruptionError, match="valid strict JSON"):
            reopened.delete(where={"kind": "target"})
        assert reopened.count() == 2

        # Unfiltered namespace deletion remains a deterministic recovery path.
        reopened.delete()
        assert reopened.count() == 0
    finally:
        reopened.close()
