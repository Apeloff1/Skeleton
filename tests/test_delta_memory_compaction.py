"""Δ-Memory bounded window + snapshot compaction (Pack J, extends #1649).

Covers gameforge-rs ``gf-gameforge::delta_memory`` parity plus the
extend-only Python surface (tombstones, batch writes, state round-trip,
snapshot persistence ports). Existing window tests live in
``tests/test_delta_memory_window.py`` and must keep passing unchanged.
"""

from __future__ import annotations

import json
import threading

import pytest

from skeleton.memory.delta_memory import (
    DEFAULT_WINDOW_CAP,
    DeltaMemory,
    DeltaMemoryStats,
    DeltaSnapshotPort,
    InMemoryDeltaSnapshotStore,
    JsonFileDeltaSnapshotStore,
    PersistingDeltaMemory,
    build_delta_memory,
)


# -- RS parity -------------------------------------------------------------


def test_default_window_cap_matches_merged_default():
    assert DEFAULT_WINDOW_CAP == 512
    assert DeltaMemory().window_cap == 512


def test_window_never_exceeds_cap():
    dm = DeltaMemory(window_cap=5)
    for i in range(103):
        dm.write(f"k{i % 7}", i)
        assert dm.stats()["window_len"] < 5
    # 103 writes / cap 5 -> 20 compactions, 3 pending deltas
    st = dm.stats()
    assert st["compactions"] == 20
    assert st["window_len"] == 3
    assert st["snapshot_keys"] == 7


def test_rs_stats_keys_preserved():
    st = DeltaMemory(window_cap=4).stats()
    for key in ("window_len", "snapshot_keys", "compactions", "window_cap"):
        assert key in st


def test_rs_last_write_wins_within_single_compaction():
    dm = DeltaMemory(window_cap=4)
    dm.write("a", 1)
    dm.write("a", 2)
    dm.write("b", 3)
    dm.write("a", 4)  # triggers compaction
    assert dm.stats()["window_len"] == 0
    assert dm.read("a") == 4
    assert dm.read("b") == 3


def test_window_cap_one_compacts_every_write():
    dm = DeltaMemory(window_cap=1)
    dm.write("a", 1)
    dm.write("b", 2)
    assert dm.stats()["compactions"] == 2
    assert dm.stats()["window_len"] == 0
    assert dm.materialize() == {"a": 1, "b": 2}


def test_negative_window_cap_rejected():
    with pytest.raises(ValueError):
        DeltaMemory(window_cap=-3)


def test_compact_on_empty_window_is_noop():
    dm = DeltaMemory(window_cap=4)
    assert dm.compact() == 0
    assert dm.stats()["compactions"] == 0


def test_none_value_is_stored_like_rs_json_null():
    dm = DeltaMemory(window_cap=4)
    dm.write("n", None)
    assert dm.read("n") is None
    assert dm.has("n")


# -- tombstones ------------------------------------------------------------


def test_delete_in_window_hides_snapshot_value():
    dm = DeltaMemory(window_cap=8)
    dm.write("k", "v")
    dm.compact()
    assert dm.delete("k") is True
    assert dm.read("k") is None
    assert "k" not in dm
    assert dm.stats()["pending_tombstones"] == 1
    dm.compact()
    assert dm.stats()["snapshot_keys"] == 0
    assert dm.stats()["pending_tombstones"] == 0


def test_delete_missing_key_returns_false():
    dm = DeltaMemory(window_cap=8)
    assert dm.delete("ghost") is False
    assert dm.stats()["deletes"] == 1


def test_delete_counts_toward_window_cap():
    dm = DeltaMemory(window_cap=2)
    dm.write("a", 1)
    dm.delete("a")  # fills window -> compacts, tombstone drops "a"
    assert dm.stats()["compactions"] == 1
    assert dm.materialize() == {}


def test_write_after_delete_resurrects():
    dm = DeltaMemory(window_cap=8)
    dm.write("a", 1)
    dm.delete("a")
    dm.write("a", 2)
    assert dm.read("a") == 2
    dm.compact()
    assert dm.read("a") == 2


# -- views / batch ---------------------------------------------------------


def test_write_many_respects_cap():
    dm = DeltaMemory(window_cap=3)
    n = dm.write_many((f"k{i}", i) for i in range(7))
    assert n == 7
    assert dm.stats()["compactions"] == 2
    assert dm.stats()["window_len"] == 1
    assert dm.stats()["writes"] == 7


def test_materialized_views_sorted_and_merged():
    dm = DeltaMemory(window_cap=10)
    dm.write("b", 2)
    dm.write("a", 1)
    dm.compact()
    dm.write("c", 3)
    dm.delete("b")
    assert dm.keys() == ["a", "c"]
    assert dm.items() == [("a", 1), ("c", 3)]
    assert dm.materialize() == {"a": 1, "c": 3}
    assert len(dm) == 2


def test_stats_obj_matches_dict():
    dm = DeltaMemory(window_cap=4)
    dm.write("a", 1)
    dm.read("a")
    obj = dm.stats_obj()
    assert isinstance(obj, DeltaMemoryStats)
    assert obj.as_dict() == dm.stats()
    assert obj.reads == 1 and obj.writes == 1


def test_clear_drops_data_keeps_counters():
    dm = DeltaMemory(window_cap=2)
    dm.write("a", 1)
    dm.write("b", 2)
    dm.clear()
    assert dm.materialize() == {}
    assert dm.stats()["compactions"] == 1


def test_repr_mentions_cap():
    assert "window_cap=7" in repr(DeltaMemory(window_cap=7))


# -- state round-trip ------------------------------------------------------


def test_export_load_roundtrip_preserves_window_and_tombstones():
    dm = DeltaMemory(window_cap=10)
    dm.write("a", 1)
    dm.compact()
    dm.write("b", {"x": 2})
    dm.delete("a")
    state = json.loads(json.dumps(dm.export_state()))

    other = DeltaMemory(window_cap=99)
    other.load_state(state)
    assert other.window_cap == 10
    assert other.materialize() == {"b": {"x": 2}}
    assert other.stats()["window_len"] == 2
    assert other.stats()["pending_tombstones"] == 1
    assert other.stats()["compactions"] == 1


def test_load_state_enforces_bounded_window():
    state = {
        "window_cap": 2,
        "snapshot": {},
        "window": [["a", 1, False], ["b", 2, False], ["c", 3, False]],
    }
    dm = DeltaMemory(window_cap=8)
    dm.load_state(state)
    assert dm.stats()["window_len"] < dm.window_cap
    assert dm.materialize() == {"a": 1, "b": 2, "c": 3}


def test_load_state_rejects_bad_payloads():
    dm = DeltaMemory(window_cap=4)
    with pytest.raises(TypeError):
        dm.load_state([])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        dm.load_state({"snapshot": ["nope"]})


def test_apply_snapshot_merge_vs_replace():
    dm = DeltaMemory(window_cap=4)
    dm.apply_snapshot({"a": 1})
    dm.apply_snapshot({"b": 2}, replace=False)
    assert dm.materialize() == {"a": 1, "b": 2}
    dm.apply_snapshot({"c": 3})
    assert dm.materialize() == {"c": 3}


# -- persistence ports -----------------------------------------------------


def test_on_compact_hook_receives_snapshot_copy():
    seen = []
    dm = DeltaMemory(window_cap=2, on_compact=seen.append)
    dm.write("a", 1)
    dm.write("b", 2)
    assert seen == [{"a": 1, "b": 2}]
    seen[0]["a"] = 999
    assert dm.read("a") == 1


def test_in_memory_store_is_a_port():
    store = InMemoryDeltaSnapshotStore()
    assert isinstance(store, DeltaSnapshotPort)
    pm = PersistingDeltaMemory(store, window_cap=2)
    pm.write("a", 1)
    assert store.saves == 0
    pm.write("b", 2)
    assert store.saves == 1
    assert store.load_snapshot() == {"a": 1, "b": 2}


def test_persisting_restores_from_port():
    store = InMemoryDeltaSnapshotStore()
    store.save_snapshot({"k": "v"})
    pm = PersistingDeltaMemory(store, window_cap=4)
    assert pm.read("k") == "v"
    assert pm.has("k")
    pm.delete("k")
    assert pm.flush() == 1
    assert store.load_snapshot() == {}
    assert isinstance(pm.inner, DeltaMemory)


def test_persisting_restore_false_ignores_port():
    store = InMemoryDeltaSnapshotStore()
    store.save_snapshot({"k": "v"})
    pm = PersistingDeltaMemory(store, window_cap=4, restore=False)
    assert pm.read("k") is None


def test_json_file_store_roundtrip(tmp_path):
    path = tmp_path / "nested" / "dm.json"
    pm = build_delta_memory(window_cap=2, persist_path=path)
    assert isinstance(pm, PersistingDeltaMemory)
    pm.write("a", 1)
    pm.write("b", [1, 2])
    assert path.exists()
    reopened = build_delta_memory(window_cap=2, persist_path=path)
    assert reopened.materialize() == {"a": 1, "b": [1, 2]}
    assert not path.with_suffix(".json.tmp").exists()


def test_json_file_store_tolerates_corrupt_or_missing(tmp_path):
    missing = JsonFileDeltaSnapshotStore(tmp_path / "missing.json")
    assert missing.load_snapshot() == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert JsonFileDeltaSnapshotStore(bad).load_snapshot() == {}


def test_build_delta_memory_plain():
    dm = build_delta_memory(window_cap=3)
    assert isinstance(dm, DeltaMemory)
    assert dm.window_cap == 3


# -- concurrency -----------------------------------------------------------


def test_concurrent_writes_stay_bounded_and_consistent():
    dm = DeltaMemory(window_cap=16)

    def worker(tid: int) -> None:
        for i in range(200):
            dm.write(f"t{tid}", i)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    st = dm.stats()
    assert st["writes"] == 1600
    assert st["window_len"] < 16
    assert st["compactions"] == 1600 // 16
    for t in range(8):
        assert dm.read(f"t{t}") == 199
