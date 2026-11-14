"""Fail-closed interactive startup when a durable action ledger is corrupted.

The campaign snapshot may still replay independently; opening a playable
terminal must not bless a mismatched action history or consume another turn.
"""
from __future__ import annotations

import sqlite3

import pytest

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def _seed_progress(store: SlotStore, name: str = "journey") -> dict:
    initial = store.new(name)
    assert initial["actions"]
    return store.step(name, initial["actions"][0], expected_head=initial["head"])


@pytest.mark.parametrize("tamper", ["delete", "wrong-head", "wrong-action"])
def test_interactive_open_refuses_corrupt_history_without_consuming_turn(tmp_path, tamper):
    store = SlotStore(tmp_path / "private")
    progressed = _seed_progress(store)
    with sqlite3.connect(store.database) as conn:
        if tamper == "delete":
            conn.execute("DELETE FROM actions WHERE slot=?", ("journey",))
        elif tamper == "wrong-head":
            conn.execute("UPDATE actions SET next_head=? WHERE slot=?", ("0" * 64, "journey"))
        else:
            conn.execute("UPDATE actions SET action=? WHERE slot=?", (b'{"verb":"retry"}', "journey"))
    calls = []
    with pytest.raises(StoreError):
        play(store, "journey", read=lambda prompt: calls.append(prompt) or "0", write=lambda line: None)
    assert calls == []
    snapshot = store.load("journey")
    assert snapshot["revision"] == progressed["revision"]
    assert snapshot["head"] == progressed["head"]


def test_clean_cold_open_audits_before_prompt_and_quit_does_not_mutate(tmp_path):
    store = SlotStore(tmp_path / "private")
    progressed = _seed_progress(store)
    prompts = []
    result = play(store, "journey", read=lambda prompt: prompts.append(prompt) or "q", write=lambda line: None)
    assert len(prompts) == 1
    assert result["head"] == progressed["head"]
    assert result["revision"] == progressed["revision"]
    assert store.audit("journey")["verified"] is True
