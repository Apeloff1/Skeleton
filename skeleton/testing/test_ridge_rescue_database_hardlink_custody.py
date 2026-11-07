"""SQLite save custody rejects hard-linked database aliases before mutation."""
from __future__ import annotations

import os

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_hard_linked_database_refused_without_touching_original(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    alias = tmp_path / "database-alias.sqlite3"
    try:
        os.link(store.database, alias)
    except (OSError, NotImplementedError):
        pytest.skip("hard links unavailable on this filesystem")
    before = alias.read_bytes()
    with pytest.raises(StoreError, match="hard-linked"):
        SlotStore(store.root).load("journey")
    with pytest.raises(StoreError, match="hard-linked"):
        SlotStore(store.root).step(
            "journey", initial["actions"][0], expected_head=initial["head"]
        )
    assert alias.read_bytes() == before
    alias.unlink()
    assert SlotStore(store.root).load("journey")["head"] == initial["head"]


def test_regular_private_database_remains_usable(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    next_state = store.step(
        "journey", initial["actions"][0], expected_head=initial["head"]
    )
    assert next_state["revision"] == 1
    assert store.audit("journey")["verified"]
