"""Bounded consumer save storage and database-failure behavior."""
from __future__ import annotations

import os
import sqlite3

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import (
    SlotStore, StoreError, MAX_SAVE_SLOTS, MAX_DATABASE_BYTES,
)


def test_save_slot_budget_is_enforced(tmp_path):
    store = SlotStore(tmp_path / "saves")
    for number in range(MAX_SAVE_SLOTS):
        store.new(f"slot{number}")
    with pytest.raises(StoreError, match="capacity"):
        store.new("overflow")
    assert store.load("slot0")["revision"] == 0


def test_database_byte_budget_fails_closed(tmp_path):
    store = SlotStore(tmp_path / "saves")
    store.new("game")
    with open(store.database, "ab") as handle:
        handle.truncate(MAX_DATABASE_BYTES + 1)
    with pytest.raises(StoreError, match="bounded storage"):
        store.load("game")


def test_corrupt_database_fails_without_reinitializing(tmp_path):
    store = SlotStore(tmp_path / "saves")
    store.new("game")
    with open(store.database, "r+b") as handle:
        handle.seek(0)
        handle.write(b"not a sqlite database")
    with pytest.raises(StoreError):
        store.load("game")
    assert store.database.exists()


def test_invalid_action_transaction_keeps_prior_head(tmp_path):
    store = SlotStore(tmp_path / "saves")
    initial = store.new("game")
    with pytest.raises(ValueError):
        store.step("game", {"verb": "fly"}, expected_head=initial["head"])
    assert store.load("game")["head"] == initial["head"]
    assert store.audit("game")["audit_entries"] == 0
