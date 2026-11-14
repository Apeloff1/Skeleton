"""Failed consumer export publication must not leave partial save artifacts."""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.game.gameplay.ridge_rescue import consumer_store
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_failed_export_fsync_removes_only_owned_partial_file(tmp_path, monkeypatch):
    store = SlotStore(tmp_path / "saves")
    store.new("game")
    original = consumer_store.os.fsync

    def fail_fsync(fd):
        raise OSError("simulated interrupted export")

    monkeypatch.setattr(consumer_store.os, "fsync", fail_fsync)
    with pytest.raises(StoreError, match="portable export write refused"):
        store.export("game")
    assert list((store.root / "exports").iterdir()) == []
    monkeypatch.setattr(consumer_store.os, "fsync", original)
    exported = store.export("game")
    assert exported.is_file()
    assert exported.read_bytes().endswith(b"\\n")


def test_failed_export_does_not_unlink_replaced_file(tmp_path, monkeypatch):
    store = SlotStore(tmp_path / "saves")
    store.new("game")
    replacement = b"replacement from concurrent publisher"
    original_fsync = consumer_store.os.fsync

    def replace_then_fail(fd):
        directory = store.root / "exports"
        files = list(directory.iterdir())
        assert len(files) == 1
        files[0].unlink()
        files[0].write_bytes(replacement)
        raise OSError("simulated concurrent replacement")

    monkeypatch.setattr(consumer_store.os, "fsync", replace_then_fail)
    with pytest.raises(StoreError, match="portable export write refused"):
        store.export("game")
    files = list((store.root / "exports").iterdir())
    assert len(files) == 1
    assert files[0].read_bytes() == replacement
    monkeypatch.setattr(consumer_store.os, "fsync", original_fsync)
