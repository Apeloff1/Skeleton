"""Backup bounds corrupt revision metadata before reading action rows."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_backup import MAX_BACKUP_ACTIONS, verify_backup
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError, _source


def test_backup_refuses_oversized_revision_before_export(tmp_path):
    store = SlotStore(tmp_path / "private")
    session = store.new("journey")
    with sqlite3.connect(store.database) as conn:
        conn.execute("UPDATE slots SET revision=? WHERE name=?",
                     (MAX_BACKUP_ACTIONS + 1, "journey"))
    with pytest.raises(StoreError, match="backup action budget"):
        store.backup("journey")
    assert store.load("journey")["head"] == session["head"]
    exports = store.root / "exports"
    assert not exports.exists() or not list(exports.glob("*.json"))


def test_valid_zero_action_backup_still_replays(tmp_path):
    store = SlotStore(tmp_path / "private")
    session = store.new("journey")
    backup = store.backup("journey")
    replayed, history = verify_backup(backup.read_bytes(), _source())
    assert history == []
    assert replayed["head"] == session["head"]
