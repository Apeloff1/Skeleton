"""End-to-end consumer source -> engine -> transactional save -> replay export."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign import verify_export
from skeleton.game.gameplay.ridge_rescue.consumer_acceptance import run_acceptance
from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_real_two_chapter_save_restart_export(tmp_path):
    result = run_acceptance(tmp_path / "saves")
    assert result["status"] == "verified-in-process"
    assert result["chapters"] == 2
    assert result["actions"] > 10
    assert result["restart_count"] == result["saved_revision"]
    assert result["portable_export_verified"]
    assert not result["windows_device_certified"]


def test_duplicate_slot_and_invalid_names_fail_closed(tmp_path):
    store = SlotStore(tmp_path / "saves")
    store.new("test")
    with pytest.raises(StoreError, match="already exists"):
        store.new("test")
    for name in ("../escape", "a/b", "", "A", "a" * 33, "a.json", "a\\b"):
        with pytest.raises(StoreError):
            store.new(name)


def test_restart_and_exact_head_cas(tmp_path):
    root = tmp_path / "saves"
    first = SlotStore(root).new("game")
    action = first["actions"][0]
    updated = SlotStore(root).step("game", action, expected_head=first["head"])
    assert updated["revision"] == 1
    assert SlotStore(root).load("game")["head"] == updated["head"]
    with pytest.raises(StoreError, match="stale"):
        SlotStore(root).step("game", action, expected_head=first["head"])
    assert SlotStore(root).audit("game")["audit_entries"] == 1


def test_tampered_session_and_source_rejected(tmp_path):
    store = SlotStore(tmp_path / "saves")
    original = store.new("game")
    with sqlite3.connect(store.database) as conn:
        raw = json.loads(conn.execute("SELECT session FROM slots WHERE name='game'").fetchone()[0])
        raw["index"] = 1
        conn.execute("UPDATE slots SET session=? WHERE name='game'", (json.dumps(raw).encode(),))
    with pytest.raises(StoreError, match="replay rejected"):
        store.load("game")
    assert original["index"] == 0


def test_tampered_audit_chain_rejected(tmp_path):
    store = SlotStore(tmp_path / "saves")
    initial = store.new("game")
    store.step("game", initial["actions"][0], expected_head=initial["head"])
    with sqlite3.connect(store.database) as conn:
        conn.execute("UPDATE actions SET next_head='wrong' WHERE slot='game'")
    with pytest.raises(StoreError, match="history head mismatch"):
        store.audit("game")


def test_export_is_portable_and_create_only(tmp_path):
    store = SlotStore(tmp_path / "saves")
    original = store.new("game")
    first = store.export("game")
    second = store.export("game")
    assert first != second and first.exists() and second.exists()
    assert verify_export(first.read_bytes())["head"] == original["head"]
    tampered = json.loads(first.read_bytes())
    tampered["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        verify_export(tampered)


def test_interactive_quit_and_resume(tmp_path):
    store = SlotStore(tmp_path / "saves")
    messages = []
    commands = iter(["0", "q"])
    first = play(store, "game", read=lambda prompt: next(commands), write=messages.append)
    assert first["revision"] == 1
    second = play(SlotStore(tmp_path / "saves"), "game",
                  read=lambda prompt: "q", write=messages.append)
    assert second["head"] == first["head"]
    assert any("Actions:" in message for message in messages)


def test_linked_save_directory_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(StoreError):
        SlotStore(link)


def test_database_link_rejected(tmp_path):
    root = tmp_path / "saves"
    store = SlotStore(root)
    store.new("game")
    database = store.database
    relocated = tmp_path / "moved.sqlite3"
    database.rename(relocated)
    try:
        database.symlink_to(relocated)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(StoreError, match="linked"):
        store.load("game")


def test_invalid_action_does_not_mutate_save(tmp_path):
    store = SlotStore(tmp_path / "saves")
    initial = store.new("game")
    with pytest.raises(ValueError):
        store.step("game", {"verb": "evacuate", "choice": "protect"}, expected_head=initial["head"])
    assert store.load("game")["head"] == initial["head"]
    assert store.audit("game")["revision"] == 0


def test_original_campaign_earned_ending_through_save(tmp_path):
    store = SlotStore(tmp_path / "saves")
    state = store.new("game")
    for action in acceptance_actions("protect"):
        state = store.step("game", action, expected_head=state["head"])
    assert state["index"] == 1
    assert state["session"]["completed"][0]["state"]["status"] == "won:protect"
