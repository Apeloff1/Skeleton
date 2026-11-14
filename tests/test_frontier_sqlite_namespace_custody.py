"""Cross-connection namespace quota and transaction regression checks."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from skeleton.frontier.runtime.memory_adapters import SQLiteCollection


def put(store, key, document="text", **metadata):
    store.add(ids=[key], documents=[document], metadatas=[metadata])


def test_batch_quota_failure_rolls_back_every_row(tmp_path):
    with SQLiteCollection(tmp_path / "memory.sqlite", capacity=2) as store:
        put(store, "existing")
        with pytest.raises(OverflowError):
            store.add(ids=["one", "two"], documents=["x", "y"], metadatas=[{}, {}])
        assert store.get()["ids"] == ["existing"]
        put(store, "existing", "replacement")
        assert store.get()["documents"] == ["replacement"]


def test_byte_budget_is_namespace_scoped_and_atomic(tmp_path):
    path = tmp_path / "memory.sqlite"
    with SQLiteCollection(path, namespace="one", max_namespace_bytes=30) as first:
        with SQLiteCollection(path, namespace="two", max_namespace_bytes=30) as second:
            put(first, "a", "x" * 20)
            put(second, "b", "y" * 20)
            with pytest.raises(OverflowError):
                put(first, "b", "z" * 20)
            assert first.count() == second.count() == 1
            assert first.get()["ids"] == ["a"]
            assert second.get()["ids"] == ["b"]


def test_concurrent_connections_cannot_overcommit_namespace(tmp_path):
    path = tmp_path / "memory.sqlite"
    with SQLiteCollection(path, capacity=1) as first:
        with SQLiteCollection(path, capacity=1) as second:
            barrier = Barrier(2)

            def attempt(pair):
                store, key = pair
                barrier.wait(timeout=5)
                try:
                    put(store, key)
                    return True
                except OverflowError:
                    return False

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(attempt, [(first, "a"), (second, "b")]))
            assert outcomes.count(True) == 1
            assert first.count() == second.count() == 1


def test_oversize_legacy_namespace_can_be_repaired_with_exact_delete(tmp_path):
    path = tmp_path / "memory.sqlite"
    with SQLiteCollection(path, capacity=3) as old:
        put(old, "a")
        put(old, "b")
    with SQLiteCollection(path, capacity=1) as current:
        with pytest.raises(OverflowError):
            current.get()
        current.delete(ids=["a"])
        assert current.get()["ids"] == ["b"]


def test_filtered_delete_preserves_unmatched_rows(tmp_path):
    with SQLiteCollection(tmp_path / "memory.sqlite") as store:
        put(store, "a", topic="retire")
        put(store, "b", topic="keep")
        store.delete(where={"topic": "retire"})
        assert store.get()["ids"] == ["b"]
