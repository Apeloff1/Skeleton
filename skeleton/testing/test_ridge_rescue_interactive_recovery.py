"""Interactive consumer recovery and export regressions for the canonical campaign.

These tests exercise the actual menu rather than calling the exporter directly.
They intentionally use separate store objects to simulate a quit/restart.
"""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.campaign import verify_export
from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_menu_export_then_restart_keeps_authoritative_head(tmp_path):
    root = tmp_path / "saves"
    store = SlotStore(root)
    first = store.new("adventure")
    messages = []
    state = play(store, "adventure", read=iter(("e", "q")).__next__,
                 write=messages.append, ascii_mode=True)
    assert state["head"] == first["head"]
    assert state["revision"] == first["revision"]
    assert any("Exported:" in message for message in messages)
    exported = list(root.rglob("*.json"))
    valid = [verify_export(path.read_bytes()) for path in exported
             if path.is_file() and path.stat().st_size > 0
             and "export" in path.name.lower()]
    assert any(bundle["head"] == first["head"] for bundle in valid)
    resumed = play(SlotStore(root), "adventure", read=lambda _: "q",
                   write=messages.append, ascii_mode=True)
    assert resumed["head"] == first["head"]
    assert SlotStore(root).audit("adventure")["revision"] == first["revision"]


def test_invalid_menu_input_does_not_consume_turn_or_change_save(tmp_path):
    root = tmp_path / "saves"
    store = SlotStore(root)
    original = store.new("adventure")
    responses = iter(("9" * 200, "-1", "?", "q"))
    messages = []
    resumed = play(store, "adventure", read=lambda _: next(responses),
                   write=messages.append, ascii_mode=True)
    assert resumed["head"] == original["head"]
    assert resumed["revision"] == 0
    assert sum("Unavailable command" in msg for msg in messages) == 2
    assert SlotStore(root).audit("adventure")["audit_entries"] == 0


def test_eof_quit_keeps_last_committed_save(tmp_path):
    root = tmp_path / "saves"
    store = SlotStore(root)
    original = store.new("adventure")
    state = play(store, "adventure", read=lambda _: (_ for _ in ()).throw(EOFError),
                 write=lambda _: None, ascii_mode=True)
    assert state["head"] == original["head"]
    assert SlotStore(root).load("adventure")["revision"] == 0
