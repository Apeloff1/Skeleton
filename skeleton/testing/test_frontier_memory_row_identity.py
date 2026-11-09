from __future__ import annotations

import sqlite3

import pytest

from skeleton.frontier.memory_adapters import (
    CollectionMemoryAdapter,
    MemoryStoreCorruptionError,
    SQLiteCollection,
)


def _rewrite_field(database, *, namespace: str, item_id: str, field: str, value) -> None:
    statements = {
        "item_id": (
            "UPDATE frontier_memory_items SET item_id = ? "
            "WHERE namespace = ? AND item_id = ?"
        ),
        "document": (
            "UPDATE frontier_memory_items SET document = ? "
            "WHERE namespace = ? AND item_id = ?"
        ),
    }
    with sqlite3.connect(database) as connection:
        connection.execute(statements[field], (value, namespace, item_id))
        connection.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("item_id", " corrupted-id ", "normalized form"),
        ("document", sqlite3.Binary(b"binary-document"), "stored as text"),
    ],
    ids=["noncanonical-id", "nontext-document"],
)
async def test_corrupt_memory_row_identity_fails_closed(
    tmp_path,
    field: str,
    value,
    message: str,
):
    database = tmp_path / "row-identity.sqlite3"
    namespace = "runtime"
    collection = SQLiteCollection(database, namespace=namespace)
    adapter = CollectionMemoryAdapter(collection)
    try:
        await adapter.put(
            {
                "id": "execution-1",
                "content": "canonical runtime memory",
                "metadata": {"domain": "runtime"},
            }
        )
    finally:
        collection.close()

    _rewrite_field(
        database,
        namespace=namespace,
        item_id="execution-1",
        field=field,
        value=value,
    )

    reopened = SQLiteCollection(database, namespace=namespace)
    try:
        with pytest.raises(MemoryStoreCorruptionError, match=message):
            CollectionMemoryAdapter(reopened)
            reopened.query(query_texts=["canonical"], n_results=5)
        assert reopened.count() == 1

        # Full namespace deletion must remain available as a repair mechanism
        # even when the row identity itself is damaged.
        reopened.delete()
        assert reopened.count() == 0
    finally:
        reopened.close()


class ProviderCollection:
    def __init__(self, result):
        self.result = result

    def add(self, *, documents, metadatas, ids):
        return None

    def query(self, *, query_texts, n_results, where=None):
        return self.result

    def delete(self, *, ids=None, where=None):
        return None


@pytest.mark.asyncio
async def test_provider_result_requires_string_document():
    adapter = CollectionMemoryAdapter(
        ProviderCollection(
            {
                "documents": [[b"bytes-not-text"]],
                "metadatas": [[{"domain": "runtime"}]],
                "ids": [["provider-1"]],
                "distances": [[0.0]],
            }
        )
    )
    with pytest.raises(TypeError, match="document must be a string"):
        await adapter.search("provider")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("item_id", "error_type", "message"),
    [
        (b"provider-1", TypeError, "memory id must be a string"),
        (" provider-1 ", ValueError, "memory id must be normalized"),
    ],
    ids=["nonstring", "noncanonical"],
)
async def test_provider_result_requires_canonical_string_id(
    item_id,
    error_type,
    message: str,
):
    adapter = CollectionMemoryAdapter(
        ProviderCollection(
            {
                "documents": [["provider result"]],
                "metadatas": [[{"domain": "runtime"}]],
                "ids": [[item_id]],
                "distances": [[0.0]],
            }
        )
    )
    with pytest.raises(error_type, match=message):
        await adapter.search("provider")


@pytest.mark.asyncio
async def test_provider_query_result_must_be_mapping():
    adapter = CollectionMemoryAdapter(ProviderCollection(["invalid", "shape"]))
    with pytest.raises(TypeError, match="query result must be a mapping"):
        await adapter.search("provider")
