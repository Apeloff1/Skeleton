"""Failed backup publication must not expose partial or foreign files."""
from __future__ import annotations

import pytest

from skeleton.game.gameplay.ridge_rescue import consumer_store
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_backup_fsync_failure_cleans_owned_partial(tmp_path, monkeypatch):
    store = SlotStore(tmp_path / "saves")
    store.new("game")
    original = consumer_store.os.fsync

    def fail(fd):
        raise OSError("simulated backup interruption")

    monkeypatch.setattr(consumer_store.os, "fsync", fail)
    with pytest.raises(StoreError, match="portable backup write refused"):
        store.backup("game")
    assert list((store.root / "exports").iterdir()) == []
    monkeypatch.setattr(consumer_store.os, "fsync", original)
    backup = store.backup("game")
    assert backup.is_file()
    assert backup.read_bytes().endswith(b"\n")


def test_backup_failure_preserves_concurrent_replacement(tmp_path, monkeypatch):
    store = SlotStore(tmp_path / "saves")
    store.new("game")
    replacement = b"other process's file"

    def replace_then_fail(fd):
        entries = list((store.root / "exports").iterdir())
        assert len(entries) == 1
        entries[0].unlink()
        entries[0].write_bytes(replacement)
        raise OSError("simulated concurrent replacement")

    monkeypatch.setattr(consumer_store.os, "fsync", replace_then_fail)
    with pytest.raises(StoreError, match="portable backup write refused"):
        store.backup("game")
    entries = list((store.root / "exports").iterdir())
    assert len(entries) == 1
    assert entries[0].read_bytes() == replacement
