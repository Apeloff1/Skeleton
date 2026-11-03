"""Read-only, consumer-facing playability and guidance contracts."""
from __future__ import annotations

from skeleton.game.gameplay.ridge_rescue.consumer_cli import play, _view
from skeleton.game.gameplay.ridge_rescue.consumer_experience import (
    navigation_hint, recent_events, status_panel,
)
from skeleton.game.gameplay.ridge_rescue.consumer_store import SlotStore
from skeleton.game.gameplay.ridge_rescue.acceptance import acceptance_actions
from skeleton.game.gameplay.ridge_rescue.campaign_acceptance import LAST_SIGNAL


def test_player_sees_story_objective_and_survival_budget(tmp_path):
    state = SlotStore(tmp_path / "saves").new("game")
    view = _view(state, ascii_mode=True)
    assert "First Evacuation" in view
    assert "Required ending: protect" in view
    assert "Health: 10/10" in view
    assert "Stamina: 8/8" in view
    assert "rescue civilians (0/1)" in view
    assert "Actions:" in view


def test_hint_help_and_journal_never_consume_turn(tmp_path):
    store = SlotStore(tmp_path / "saves")
    messages = []
    commands = iter(["h", "?", "j", "q"])
    state = play(store, "game", read=lambda _: next(commands), write=messages.append)
    assert state["revision"] == 0
    assert state["state"]["turn"] == 0
    assert SlotStore(tmp_path / "saves").load("game")["head"] == state["head"]
    assert any("Advisory only" in message for message in messages)
    assert any("Numbers perform listed actions" in message for message in messages)
    assert any("Recent events:" in message for message in messages)


def test_guidance_uses_replay_verified_state_after_restart(tmp_path):
    root = tmp_path / "saves"
    store = SlotStore(root)
    first = store.new("game")
    action = first["actions"][0]
    changed = store.step("game", action, expected_head=first["head"])
    reloaded = SlotStore(root).load("game")
    assert changed["head"] == reloaded["head"]
    assert reloaded["revision"] == 1
    assert "Turn: 1/" in status_panel(reloaded)
    assert "Recent events:" in recent_events(reloaded)
    assert "Advisory only" in navigation_hint(reloaded)


def test_completed_game_shows_earned_endings_and_no_fake_route(tmp_path):
    store = SlotStore(tmp_path / "saves")
    state = store.new("game")
    for action in acceptance_actions("protect") + LAST_SIGNAL:
        state = store.step("game", action, expected_head=state["head"])
    assert state["status"] == "completed"
    assert "won:protect" in status_panel(state)
    assert "won:salvage" in status_panel(state)
    assert "No active route" in navigation_hint(state)
    assert "Victory:" in _view(state)
