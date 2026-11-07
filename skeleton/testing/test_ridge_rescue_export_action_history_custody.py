"""Portable exports refuse a tampered durable action ledger."""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


@pytest.mark.parametrize("tamper", ["delete", "action", "head"])
def test_export_refuses_tampered_history_without_publishing(tmp_path, tamper):
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    progressed = store.step("journey", initial["actions"][0], expected_head=initial["head"])
    with sqlite3.connect(store.database) as connection:
        if tamper == "delete":
            connection.execute("DELETE FROM actions WHERE slot=?", ("journey",))
        elif tamper == "action":
            connection.execute("UPDATE actions SET action=? WHERE slot=?", (b'{"verb":"retry"}', "journey"))
        else:
            connection.execute("UPDATE actions SET next_head=? WHERE slot=?", ("0" * 64, "journey"))
    with pytest.raises(StoreError):
        store.export("journey")
    assert not list((store.root / "exports").glob("*.json")) if (store.root / "exports").exists() else True
    assert store.load("journey")["head"] == progressed["head"]


def test_export_of_intact_history_is_replay_verified(tmp_path):
    from skeleton.game.gameplay.ridge_rescue.campaign import verify_export
    store = SlotStore(tmp_path / "private")
    initial = store.new("journey")
    progressed = store.step("journey", initial["actions"][0], expected_head=initial["head"])
    path = store.export("journey")
    assert path.is_file()
    assert verify_export(path.read_bytes())["head"] == progressed["head"]
