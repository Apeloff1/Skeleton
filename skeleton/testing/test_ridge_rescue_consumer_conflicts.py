"""Consumer terminal safety under concurrent writers and recoverable failures."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import _view, play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError
from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import LAST_SIGNAL


def test_concurrent_turn_is_never_replayed_from_stale_menu(tmp_path):
    store = SlotStore(tmp_path / "saves")
    initial = store.new("game")
    offered = initial["actions"][0]
    responses = iter(["0", "q"])
    first = [True]
    lines = []

    def read(_prompt):
        if first[0]:
            first[0] = False
            latest = store.load("game")
            store.step("game", offered, expected_head=latest["head"])
        return next(responses)

    final = play(store, "game", read=read, write=lines.append)
    assert final["revision"] == 1
    assert final["head"] == store.load("game")["head"]
    assert store.audit("game")["audit_entries"] == 1
    assert any("Action not saved; refreshing authoritative slot" in line for line in lines)


def test_export_failure_does_not_consume_turn_or_exit_play(tmp_path, monkeypatch):
    store = SlotStore(tmp_path / "saves")
    initial = store.new("game")
    lines = []

    def fail_export(_slot):
        raise StoreError("export device unavailable")

    monkeypatch.setattr(store, "export", fail_export)
    answers = iter(["e", "q"])
    final = play(store, "game", read=lambda _prompt: next(answers),
                 write=lines.append)
    assert final["head"] == initial["head"]
    assert final["revision"] == 0
    assert any("Export unavailable; saved game unchanged" in line for line in lines)


def test_completed_view_has_valid_chapter_number_and_ascii_fallback(tmp_path):
    store = SlotStore(tmp_path / "saves")
    current = store.new("game")
    for action in acceptance_actions("protect") + LAST_SIGNAL:
        current = store.step("game", action, expected_head=current["head"])
    rendered = _view(current, ascii_mode=True)
    assert rendered.isascii()
    assert "Chapter: 2/2" in rendered
    assert "Victory:" in rendered
    assert "Chapter: 3/2" not in rendered
