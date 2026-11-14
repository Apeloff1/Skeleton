"""Audit bounds corrupt metadata and action-table growth before replay."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_backup import MAX_BACKUP_ACTIONS
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_audit_rejects_oversized_revision_without_reading_history(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    with sqlite3.connect(store.database) as conn:
        conn.execute("UPDATE slots SET revision=? WHERE name=?",
                     (MAX_BACKUP_ACTIONS + 1, "journey"))
    with pytest.raises(StoreError, match="audit action budget"):
        store.audit("journey")
    assert store.load("journey")["head"] == initial["head"]


def test_audit_rejects_extra_action_rows_without_mutating_slot(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    with sqlite3.connect(store.database) as conn:
        conn.execute(
            "INSERT INTO actions(slot, revision, prior_head, next_head, action) "
            "VALUES(?,?,?,?,?)",
            ("journey", 1, initial["head"], initial["head"], b'{"verb":"retry"}'),
        )
    with pytest.raises(StoreError, match="save history is incomplete"):
        store.audit("journey")
    assert store.load("journey")["head"] == initial["head"]


def test_valid_zero_action_audit_remains_replayable(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    audit = store.audit("journey")
    assert audit["verified"] is True
    assert audit["audit_entries"] == 0
    assert audit["head"] == initial["head"]
