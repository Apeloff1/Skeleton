"""Windowed Δ-Memory — gameforge-rs delta_memory port."""

from __future__ import annotations

import pytest

from skeleton.memory.delta_memory import DeltaMemory


def test_write_read_from_window():
    dm = DeltaMemory(window_cap=8)
    dm.write("a", {"n": 1})
    assert dm.read("a") == {"n": 1}
    assert dm.stats()["window_len"] == 1
    assert dm.stats()["compactions"] == 0


def test_window_overrides_snapshot():
    dm = DeltaMemory(window_cap=4)
    dm.write("k", "old")
    dm.compact()
    assert dm.stats()["snapshot_keys"] == 1
    dm.write("k", "new")
    assert dm.read("k") == "new"


def test_auto_compact_on_cap():
    dm = DeltaMemory(window_cap=3)
    dm.write("a", 1)
    dm.write("b", 2)
    dm.write("c", 3)
    st = dm.stats()
    assert st["window_len"] == 0
    assert st["snapshot_keys"] == 3
    assert st["compactions"] == 1
    assert dm.read("b") == 2


def test_later_write_wins_across_compaction():
    dm = DeltaMemory(window_cap=2)
    dm.write("x", 1)
    dm.write("x", 2)  # triggers compact; last write wins in snapshot
    assert dm.read("x") == 2
    assert dm.stats()["compactions"] == 1


def test_missing_key():
    dm = DeltaMemory(window_cap=4)
    assert dm.read("nope") is None


def test_window_cap_rejects_zero():
    with pytest.raises(ValueError):
        DeltaMemory(window_cap=0)
