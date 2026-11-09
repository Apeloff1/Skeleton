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
    "value",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
async def test_memory_metadata_rejects_non_finite_numbers_consistently(
    backend: str,
    tmp_path,
    value: float,
):
    assert not math.isfinite(value)
    store, collection = _store(backend, tmp_path, f"nonfinite-{backend}")
    try:
        with pytest.raises(ValueError, match="must be finite"):
            await store.put(
                {
                    "id": "invalid-number",
                    "content": "strict metadata boundary",
                    "metadata": {"score": value},
                }
            )
    finally:
        if collection is not None:
            assert collection.count() == 0
            collection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
@pytest.mark.parametrize(
    ("metadata", "error_type", "message"),
    [
        ({"raw": b"bytes"}, TypeError, "JSON-compatible"),
        ({"coords": (1, 2)}, TypeError, "JSON-compatible"),
        ({"nested": {1: "value"}}, TypeError, "object key"),
        ({"members": {"a", "b"}}, TypeError, "JSON-compatible"),
    ],
    ids=["bytes", "tuple", "non-string-key", "set"],
)
async def test_memory_metadata_rejects_non_json_types_consistently(
    backend: str,
    tmp_path,
    metadata,
    error_type,
    message: str,
):
    store, collection = _store(backend, tmp_path, f"invalid-json-{backend}")
    try:
        with pytest.raises(error_type, match=message):
            await store.put(
                {
                    "id": "invalid-json",
                    "content": "strict metadata boundary",
                    "metadata": metadata,
                }
            )
    finally:
        if collection is not None:
            assert collection.count() == 0
            collection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
async def test_memory_metadata_rejects_cycles_consistently(backend: str, tmp_path):
    cyclic: list[object] = []
    cyclic.append(cyclic)
    store, collection = _store(backend, tmp_path, f"cycle-{backend}")
    try:
        with pytest.raises(ValueError, match="must not contain cycles"):
            await store.put(
                {
                    "id": "cyclic",
                    "content": "strict metadata boundary",
                    "metadata": {"cycle": cyclic},
                }
            )
    finally:
        if collection is not None:
            assert collection.count() == 0
            collection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("backend", ["reference", "sqlite"])
async def test_nested_json_metadata_roundtrips_without_backend_type_drift(
    backend: str,
    tmp_path,
):
    store, collection = _store(backend, tmp_path, f"nested-{backend}")
    metadata = {
        "domain": "runtime",
        "flags": [True, False, None],
        "metrics": {"attempt": 3, "score": 0.75},
        "labels": ["frontier", "durable"],
    }
    try:
        await store.put(
            {
                "id": "nested-json",
                "content": "nested portable metadata",
                "metadata": metadata,
            }
        )
        hits = await store.search("nested portable")
        assert len(hits) == 1
        assert hits[0]["metadata"] == metadata
    finally:
        if collection is not None:
            collection.close()
