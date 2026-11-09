from __future__ import annotations

import math

import pytest

from skeleton.frontier.memory import InMemoryStore
from skeleton.frontier.memory_adapters import CollectionMemoryAdapter, SQLiteCollection


def _store(backend: str, tmp_path, name: str):
    if backend == "reference":
        return InMemoryStore(), None
    collection = SQLiteCollection(tmp_path / f"{name}.sqlite3", namespace=name)
    return CollectionMemoryAdapter(collection), collection


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
@pytest.mark.parametrize(
    ("filters", "error_type", "message"),
    [
        ({"coords": (1, 2)}, TypeError, "JSON-compatible"),
        ({"score": float("nan")}, ValueError, "must be finite"),
        ({"nested": {1: "value"}}, TypeError, "object key"),
        ({"members": {"a"}}, TypeError, "JSON-compatible"),
    ],
    ids=["tuple", "nan", "non-string-key", "set"],
)
async def test_memory_filters_reject_non_portable_values_consistently(
    backend: str,
    tmp_path,
    filters,
    error_type,
    message: str,
):
    if "score" in filters:
        assert not math.isfinite(filters["score"])
    store, collection = _store(backend, tmp_path, f"filter-{backend}")
    try:
        await store.put(
            {
                "id": "portable",
                "content": "portable memory filter",
                "metadata": {"domain": "runtime"},
            }
        )
        with pytest.raises(error_type, match=message):
            await store.search("portable", filters=filters)
    finally:
        if collection is not None:
            assert collection.count() == 1
            collection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
async def test_nested_json_filters_have_identical_backend_semantics(backend: str, tmp_path):
    store, collection = _store(backend, tmp_path, f"nested-filter-{backend}")
    try:
        await store.put(
            {
                "id": "matching",
                "content": "nested filter target",
                "metadata": {
                    "selector": {"region": "north", "risk": [1, 2]},
                    "active": True,
                },
            }
        )
        await store.put(
            {
                "id": "other",
                "content": "nested filter target",
                "metadata": {
                    "selector": {"region": "south", "risk": [1, 2]},
                    "active": True,
                },
            }
        )

        hits = await store.search(
            "nested filter",
            filters={"selector": {"region": "north", "risk": [1, 2]}},
        )
        assert [hit["id"] for hit in hits] == ["matching"]
    finally:
        if collection is not None:
            collection.close()


class ProviderCollection:
    def __init__(self, result):
        self.result = result
        self.where = None

    def add(self, *, documents, metadatas, ids):
        return None

    def query(self, *, query_texts, n_results, where=None):
        self.where = where
        return self.result

    def delete(self, *, ids=None, where=None):
        return None


@pytest.mark.asyncio
async def test_collection_adapter_revalidates_provider_metadata():
    collection = ProviderCollection(
        {
            "documents": [["provider result"]],
            "metadatas": [[{"coords": (1, 2)}]],
            "ids": [["provider-1"]],
            "distances": [[0.1]],
        }
    )
    adapter = CollectionMemoryAdapter(collection)

    with pytest.raises(TypeError, match="JSON-compatible"):
        await adapter.search("provider")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "distance",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
async def test_collection_adapter_rejects_non_finite_provider_distances(distance: float):
    collection = ProviderCollection(
        {
            "documents": [["provider result"]],
            "metadatas": [[{"domain": "runtime"}]],
            "ids": [["provider-1"]],
            "distances": [[distance]],
        }
    )
    adapter = CollectionMemoryAdapter(collection)

    with pytest.raises(ValueError, match="distance must be finite"):
        await adapter.search("provider")


@pytest.mark.asyncio
async def test_collection_adapter_passes_normalized_filters_to_provider():
    collection = ProviderCollection(
        {
            "documents": [[]],
            "metadatas": [[]],
            "ids": [[]],
            "distances": [[]],
        }
    )
    adapter = CollectionMemoryAdapter(collection)

    await adapter.search(
        "provider",
        filters={"selector": {"region": "north", "risk": [1, 2]}},
    )
    assert collection.where == {"selector": {"region": "north", "risk": [1, 2]}}
