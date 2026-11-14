"""Sync must not adopt an unaudited save revision after interactive startup."""
from __future__ import annotations

import sqlite3

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_sync_refuses_concurrently_corrupted_action_history(tmp_path):
    store = SlotStore(tmp_path / "private")
    original = store.new("journey")
    prompts = []
    messages = []

    def read(prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            # Simulate another process committing a legitimate action after
            # initial audit, then damaging only the durable action ledger.
            updated = SlotStore(store.root).step(
                "journey", original["actions"][0], expected_head=original["head"]
            )
            with sqlite3.connect(store.database) as conn:
                conn.execute(
                    "UPDATE actions SET next_head=? WHERE slot=? AND revision=?",
                    ("0" * 64, "journey", updated["revision"]),
                )
            return "s"
        return "q"

    result = play(store, "journey", read=read, write=messages.append)
    assert result["head"] == original["head"]
    assert result["revision"] == original["revision"]
    assert len(prompts) == 2
    assert any("Save refresh unavailable" in message for message in messages)
    # The authoritative session was not destroyed or overwritten.
    assert store.load("journey")["revision"] == 1


def test_sync_of_clean_concurrent_progress_adopts_audited_head(tmp_path):
    store = SlotStore(tmp_path / "private")
    original = store.new("journey")
    prompts = []
    messages = []

    def read(prompt):
        prompts.append(prompt)
        if len(prompts) == 1:
            SlotStore(store.root).step(
                "journey", original["actions"][0], expected_head=original["head"]
            )
            return "s"
        return "q"

    result = play(store, "journey", read=read, write=messages.append)
    assert result["revision"] == 1
    assert result["head"] == store.audit("journey")["head"]
    assert any("Authoritative save refreshed" in message for message in messages)
