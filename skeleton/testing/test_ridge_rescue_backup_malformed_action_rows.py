"""Portable backup rejects malformed action rows without leaking parser errors."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError
from skeleton.game.gameplay.ridge_rescue.consumer_backup import verify_backup


@pytest.mark.parametrize("raw", [
    b"{",
    b"\\xff",
    b"[]",
    b'{"verb":"retry"} ',
    b"null",
    b"x" * 4097,
])
def test_backup_rejects_invalid_action_rows_without_publishing(tmp_path, raw):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    advanced = store.step(
        "journey", initial["actions"][0], expected_head=initial["head"]
    )
    with sqlite3.connect(store.database) as connection:
        connection.execute(
            "UPDATE actions SET action=? WHERE slot=? AND revision=1",
            (raw, "journey"),
        )

    with pytest.raises(StoreError, match="save history"):
        store.backup("journey")

    assert store.load("journey")["head"] == advanced["head"]
    exports = store.root / "exports"
    assert not exports.exists() or not list(exports.glob("*.json"))


def test_valid_backup_still_replays_after_parser_hardening(tmp_path):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    advanced = store.step(
        "journey", initial["actions"][0], expected_head=initial["head"]
    )
    backup = store.backup("journey")
    session, history = verify_backup(backup.read_bytes(), store_source())
    assert session["head"] == advanced["head"]
    assert len(history) == 1


def store_source():
    from skeleton.game.gameplay.ridge_rescue.consumer_store import _source
    return _source()
