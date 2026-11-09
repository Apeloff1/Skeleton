"""Δ-Memory snapshot store robustness + metrics hooks (Pack J, round 2)."""

from __future__ import annotations

import json
import math
import threading

import pytest

from skeleton.memory.delta_memory import (
    SNAPSHOT_FILE_VERSION,
    DeltaMemory,
    DeltaMetricsSink,
    InMemoryDeltaSnapshotStore,
    JsonFileDeltaSnapshotStore,
    PersistingDeltaMemory,
)
from skeleton.observability.metrics_registry import MetricsRegistry


# -- atomic JSON writes ------------------------------------------------------


def test_save_writes_versioned_checksummed_payload(tmp_path):
    store = JsonFileDeltaSnapshotStore(tmp_path / "s.json")
    store.save_snapshot({"b": 2, "a": [1]})
    raw = json.loads((tmp_path / "s.json").read_text())
    assert raw["version"] == SNAPSHOT_FILE_VERSION
    assert len(raw["sha256"]) == 64
    assert store.load_snapshot() == {"a": [1], "b": 2}


def test_save_leaves_no_temp_files_and_keeps_previous_as_backup(tmp_path):
    path = tmp_path / "s.json"
    store = JsonFileDeltaSnapshotStore(path)
    store.save_snapshot({"v": 1})
    store.save_snapshot({"v": 2})
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["s.json", "s.json.bak"]
    assert JsonFileDeltaSnapshotStore(store.backup_path).load_snapshot() == {"v": 1}


def test_failed_serialization_never_touches_disk(tmp_path):
    path = tmp_path / "s.json"
    store = JsonFileDeltaSnapshotStore(path, strict=True)
    store.save_snapshot({"ok": 1})
    before = path.read_bytes()
    with pytest.raises(ValueError):
        store.save_snapshot({"bad": math.nan})
    with pytest.raises(TypeError):
        store.save_snapshot({"bad": object()})
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["s.json"]
    assert store.saves == 1


def test_non_strict_mode_keeps_default_str_backcompat(tmp_path):
    store = JsonFileDeltaSnapshotStore(tmp_path / "s.json")
    store.save_snapshot({"p": tmp_path})
    assert store.load_snapshot()["p"] == str(tmp_path)


def test_crash_during_replace_removes_temp_and_preserves_primary(tmp_path, monkeypatch):
    path = tmp_path / "s.json"
    store = JsonFileDeltaSnapshotStore(path)
    store.save_snapshot({"v": 1})
    import skeleton.memory.delta_memory as dm_mod

    real_replace = dm_mod.os.replace

    def boom(src, dst):
        if str(dst) == str(path):
            raise OSError("disk full")
        return real_replace(src, dst)

    monkeypatch.setattr(dm_mod.os, "replace", boom)
    with pytest.raises(OSError):
        store.save_snapshot({"v": 2})
    monkeypatch.setattr(dm_mod.os, "replace", real_replace)
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert store.load_snapshot() == {"v": 1}


def test_concurrent_saves_are_serialized_and_file_stays_valid(tmp_path):
    path = tmp_path / "s.json"
    store = JsonFileDeltaSnapshotStore(path, fsync=False)
    errors = []

    def worker(tid):
        try:
            for i in range(40):
                store.save_snapshot({"tid": tid, "i": i, "pad": "x" * 512})
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert store.saves == 240
    snap = JsonFileDeltaSnapshotStore(path).load_snapshot()
    assert snap["i"] == 39 and snap["pad"] == "x" * 512
    assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]


# -- corrupt-file recovery ---------------------------------------------------


@pytest.mark.parametrize(
    "garbage",
    [
        "{not json",
        "",
        "[1, 2]",
        '{"version": 2, "snapshot": [1]}',
        '{"version": 99, "snapshot": {}}',
        '{"version": 2, "sha256": "00", "snapshot": {"a": 1}}',
        '{"version": 2, "snapshot": {"a": 1}}',
    ],
)
def test_corrupt_primary_is_quarantined_and_backup_recovered(tmp_path, garbage):
    path = tmp_path / "s.json"
    store = JsonFileDeltaSnapshotStore(path)
    store.save_snapshot({"good": 1})
    store.save_snapshot({"good": 2})  # .bak now holds {"good": 1}
    path.write_text(garbage, encoding="utf-8")
    fresh = JsonFileDeltaSnapshotStore(path)
    assert fresh.load_snapshot() == {"good": 1}
    assert fresh.recoveries == 1
    assert len(fresh.quarantined) == 1
    assert fresh.quarantined[0].read_text(encoding="utf-8") == garbage
    assert not path.exists()
    assert fresh.last_error
    fresh.save_snapshot({"good": 3})  # next save heals the primary
    assert JsonFileDeltaSnapshotStore(path).load_snapshot() == {"good": 3}


def test_bit_flip_in_value_fails_checksum(tmp_path):
    path = tmp_path / "s.json"
    store = JsonFileDeltaSnapshotStore(path, keep_backup=False)
    store.save_snapshot({"hp": 100})
    path.write_text(path.read_text().replace("100", "999"), encoding="utf-8")
    assert store.load_snapshot() == {}
    assert len(store.quarantined) == 1


def test_corrupt_primary_and_backup_returns_empty(tmp_path):
    path = tmp_path / "s.json"
    store = JsonFileDeltaSnapshotStore(path)
    store.save_snapshot({"a": 1})
    store.save_snapshot({"a": 2})
    path.write_text("x", encoding="utf-8")
    store.backup_path.write_text("y", encoding="utf-8")
    assert store.load_snapshot() == {}
    assert len(store.quarantined) == 2


def test_v1_and_bare_legacy_payloads_still_load(tmp_path):
    v1 = tmp_path / "v1.json"
    v1.write_text(json.dumps({"snapshot": {"a": 1}, "version": 1}))
    assert JsonFileDeltaSnapshotStore(v1).load_snapshot() == {"a": 1}
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"a": 2}))
    assert JsonFileDeltaSnapshotStore(bare).load_snapshot() == {"a": 2}


def test_persisting_memory_restores_from_backup_after_corruption(tmp_path):
    path = tmp_path / "dm.json"
    first = PersistingDeltaMemory(JsonFileDeltaSnapshotStore(path), window_cap=2)
    first.write("a", 1)
    first.write("b", 2)  # compaction 1 -> primary
    first.write("c", 3)
    first.write("d", 4)  # compaction 2 -> primary, compaction 1 -> .bak
    path.write_text("torn", encoding="utf-8")
    second = PersistingDeltaMemory(JsonFileDeltaSnapshotStore(path), window_cap=2)
    assert second.materialize() == {"a": 1, "b": 2}


# -- persist failure accounting ----------------------------------------------


class _FlakyPort(InMemoryDeltaSnapshotStore):
    def __init__(self):
        super().__init__()
        self.fail = False

    def save_snapshot(self, snapshot):
        if self.fail:
            raise OSError("EIO")
        super().save_snapshot(snapshot)


def test_persist_failure_is_loud_consistent_and_retryable():
    port = _FlakyPort()
    pdm = PersistingDeltaMemory(port, window_cap=2)
    port.fail = True
    pdm.write("a", 1)
    with pytest.raises(OSError):
        pdm.write("b", 2)  # triggers compaction -> save fails
    assert pdm.read("a") == 1 and pdm.read("b") == 2  # memory consistent
    st = pdm.stats()
    assert st["persist_failures"] == 1 and st["dirty"] is True
    assert "EIO" in pdm.last_persist_error


def test_flush_retries_dirty_snapshot_even_with_empty_window():
    port = _FlakyPort()
    pdm = PersistingDeltaMemory(port, window_cap=2)
    port.fail = True
    pdm.write("a", 1)
    with pytest.raises(OSError):
        pdm.write("b", 2)
    with pytest.raises(OSError):
        pdm.flush()  # still failing -> still dirty
    assert pdm.persist_failures == 2 and pdm.dirty
    port.fail = False
    assert pdm.flush() == 0
    assert not pdm.dirty
    assert port.load_snapshot() == {"a": 1, "b": 2}
    saves = port.saves
    pdm.flush()  # clean + empty window -> no redundant save
    assert port.saves == saves


def test_persisting_passthroughs_match_inner():
    pdm = PersistingDeltaMemory(InMemoryDeltaSnapshotStore(), window_cap=4, json_values=True)
    assert pdm.write_many([("a", 1), ("n", None)]) == 2
    assert pdm.lookup("n") == (True, None)
    assert pdm.get("zz", 5) == 5
    assert pdm.keys() == ["a", "n"] and len(pdm) == 2 and "a" in pdm
    assert pdm.items() == [("a", 1), ("n", None)]


# -- metrics hooks -----------------------------------------------------------


def test_metrics_registry_satisfies_sink_and_receives_counters():
    reg = MetricsRegistry()
    assert isinstance(reg, DeltaMetricsSink)
    labels = {"plane": "zaibatsu"}
    dm = DeltaMemory(window_cap=3, metrics=reg, metrics_labels=labels)
    for i in range(7):
        dm.write(f"k{i % 2}", i)
    dm.read("k0")
    dm.lookup("k1")
    dm.delete("k0")
    assert reg.get_counter("delta_memory_writes", labels) == 7
    assert reg.get_counter("delta_memory_reads", labels) == 2
    assert reg.get_counter("delta_memory_deletes", labels) == 1
    assert reg.get_counter("delta_memory_compactions", labels) == dm.compactions == 2
    assert reg.get_gauge("delta_memory_snapshot_keys", labels) == 2
    assert reg.histogram_stats("delta_memory_compaction_deltas", labels=labels)["count"] == 2
    st = dm.publish_metrics()
    assert reg.get_gauge("delta_memory_window_len", labels) == st["window_len"]
    assert reg.get_gauge("delta_memory_pending_tombstones", labels) == 1


def test_broken_metrics_sink_never_breaks_data_path():
    class Broken:
        def counter(self, *a, **k):
            raise RuntimeError("down")

        gauge = observe = counter

    dm = DeltaMemory(window_cap=2, metrics=Broken())
    dm.write("a", 1)
    dm.write("b", 2)
    assert dm.read("a") == 1 and dm.compactions == 1
    assert dm.metrics_errors > 0


def test_persist_failures_are_counted_in_metrics():
    reg = MetricsRegistry()
    port = _FlakyPort()
    pdm = PersistingDeltaMemory(port, window_cap=1, metrics=reg, metrics_prefix="dm")
    port.fail = True
    with pytest.raises(OSError):
        pdm.write("a", 1)
    assert reg.get_counter("dm_persist_failures") == 1
    assert pdm.publish_metrics()["persist_failures"] == 1
