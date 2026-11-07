"""The gameplay mutation boundary must preserve the finite replay budget."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_backup import MAX_BACKUP_ACTIONS
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_action_budget_rejects_step_before_mutating_slot(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    with sqlite3.connect(store.database) as conn:
        conn.execute("UPDATE slots SET revision=? WHERE name=?",
                     (MAX_BACKUP_ACTIONS, "journey"))
    with pytest.raises(StoreError, match="action budget exhausted"):
        store.step("journey", initial["actions"][0], expected_head=initial["head"])
    with sqlite3.connect(store.database) as conn:
        assert conn.execute("SELECT revision, head FROM slots WHERE name=?",
                            ("journey",)).fetchone() == (MAX_BACKUP_ACTIONS, initial["head"])
        assert conn.execute("SELECT COUNT(*) FROM actions WHERE slot=?",
                            ("journey",)).fetchone()[0] == 0


def test_action_budget_rejects_retry_before_mutating_slot(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    with sqlite3.connect(store.database) as conn:
        conn.execute("UPDATE slots SET revision=? WHERE name=?",
                     (MAX_BACKUP_ACTIONS, "journey"))
    with pytest.raises(StoreError, match="action budget exhausted"):
        store.retry("journey", expected_head=initial["head"])
    with sqlite3.connect(store.database) as conn:
        assert conn.execute("SELECT revision, head FROM slots WHERE name=?",
                            ("journey",)).fetchone() == (MAX_BACKUP_ACTIONS, initial["head"])


def test_normal_transition_remains_available(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    result = store.step("journey", initial["actions"][0], expected_head=initial["head"])
    assert result["revision"] == 1
    assert store.audit("journey")["verified"] is True
