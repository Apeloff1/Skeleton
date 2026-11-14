"""Interactive backup is non-mutating and recoverable on storage errors."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore, StoreError


def test_interactive_backup_keeps_current_game_revision(tmp_path):
    store = SlotStore(tmp_path / "saves")
    initial = store.new("game")
    answers = iter(["b", "q"])
    lines = []
    final = play(store, "game", read=lambda _: next(answers), write=lines.append)
    assert final["head"] == initial["head"]
    assert final["revision"] == 0
    assert any("Backup created:" in line for line in lines)
    assert store.audit("game")["verified"]


def test_interactive_backup_error_does_not_discard_save(tmp_path, monkeypatch):
    store = SlotStore(tmp_path / "saves")
    initial = store.new("game")

    def fail(_slot):
        raise StoreError("backup medium unavailable")

    monkeypatch.setattr(store, "backup", fail)
    answers = iter(["b", "q"])
    lines = []
    final = play(store, "game", read=lambda _: next(answers), write=lines.append)
    assert final["head"] == initial["head"]
    assert final["revision"] == 0
    assert any("Backup unavailable; saved game unchanged" in line for line in lines)
