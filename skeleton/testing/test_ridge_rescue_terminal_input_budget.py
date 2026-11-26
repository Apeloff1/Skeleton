"""Adversarial consumer terminal inputs must not kill or mutate a save."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import (
    MAX_MENU_DIGITS, MAX_TERMINAL_INPUT, _action_index, play,
)
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore


def test_action_index_is_bounded_and_ascii_only():
    assert _action_index("0", 1) == 0
    assert _action_index("1", 1) is None
    assert _action_index("9" * 5000, 4) is None
    assert _action_index("1" * (MAX_MENU_DIGITS + 1), 4) is None
    assert _action_index("١", 4) is None
    assert _action_index("-1", 4) is None
    assert _action_index("", 4) is None


def test_bad_pasted_commands_leave_save_intact_and_game_remains_playable(tmp_path):
    store = SlotStore(tmp_path / "saves")
    original = store.new("game")
    bad = ["9" * 5000, "1" * MAX_TERMINAL_INPUT,
           "x" * (MAX_TERMINAL_INPUT + 1), "١", "-1", "not-a-command"]
    answers = iter(bad + ["0", "q"])
    frames = []
    final = play(store, "game", read=lambda _: next(answers),
                 write=frames.append, ascii_mode=True)
    assert final["revision"] == 1
    assert final["head"] != original["head"]
    assert store.audit("game")["audit_entries"] == 1
    assert sum("Unavailable command; no turn was consumed." in line
               for line in frames) == len(bad)


def test_invalid_inputs_then_quit_do_not_create_any_turn(tmp_path):
    store = SlotStore(tmp_path / "saves")
    original = store.new("game")
    answers = iter(["9" * 5000, "١", "q"])
    final = play(store, "game", read=lambda _: next(answers),
                 write=lambda _: None)
    assert final["head"] == original["head"]
    assert final["revision"] == 0
    assert store.audit("game")["audit_entries"] == 0
