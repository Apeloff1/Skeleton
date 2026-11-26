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

def test_action_menu_is_readable_without_raw_json(tmp_path):
    from skeleton.game.gameplay.ridge_rescue.consumer_experience import action_label
    state = SlotStore(tmp_path / "saves").new("game")
    labels = [action_label(action) for action in state["actions"]]
    assert labels
    assert all(label and not label.startswith("{") for label in labels)
    assert "Actions:" in _view(state)
    assert any(label in _view(state) for label in labels)


def test_closed_action_labels_reject_unknown_verbs():
    from skeleton.game.gameplay.ridge_rescue.consumer_experience import action_label
    import pytest
    with pytest.raises(ValueError, match="unsupported"):
        action_label({"verb": "execute"})

def test_real_python_module_cli_process_quit_restart_ending_export(tmp_path):
    """Exercise the shipped module entrypoint across independent processes.

    This is a host-Python integration test, not Windows device certification.
    """
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    from skeleton.game.gameplay.ridge_rescue.campaign import (
        open_campaign, verify_campaign, step_campaign, verify_export,
    )
    from skeleton.game.gameplay.ridge_rescue.consumer_store import _source

    env = os.environ.copy()
    base = tmp_path / "appdata"
    base.mkdir()
    if os.name == "nt":
        env["LOCALAPPDATA"] = str(base)
    else:
        env["XDG_DATA_HOME"] = str(base)
    argv = [
        sys.executable, "-m", "skeleton.game.gameplay.ridge_rescue",
        "consumer",
    ]

    def invoke(command, *, input_text=None):
        proc = subprocess.run(
            argv + command, input=input_text, text=True,
            capture_output=True, env=env, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    session = open_campaign(_source())
    numbers = []
    for action in acceptance_actions("protect") + LAST_SIGNAL:
        current = verify_campaign(session)
        assert action in current["actions"]
        numbers.append(str(current["actions"].index(action)))
        session = step_campaign(session, action, expected_head=session["head"])
    split = max(1, len(numbers) // 2)
    first = invoke(["play", "--slot", "game"], input_text="\n".join(numbers[:split] + ["q"]) + "\n")
    assert "Actions:" in first
    midway = json.loads(invoke(["status", "--slot", "game"]))
    assert midway["revision"] == split
    assert midway["status"] == "playing"
    second = invoke(["play", "--slot", "game"], input_text="\n".join(numbers[split:] + ["q"]) + "\n")
    assert "Victory:" in second
    finished = json.loads(invoke(["status", "--slot", "game"]))
    assert finished["status"] == "completed"
    assert finished["head"] == session["head"]
    export = json.loads(invoke(["export", "--slot", "game"]))
    payload = Path(export["path"]).read_bytes()
    assert verify_export(payload)["head"] == session["head"]
