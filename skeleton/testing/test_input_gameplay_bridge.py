"""Cross-plane original game input, movement, collision and save acceptance."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session
from skeleton.game.presentation.flgb_presentation_runtime import (
    PresentationContractError,
)
from skeleton.game.presentation.input_router import InputProfile
from skeleton.game.presentation.input_gameplay_bridge import (
    SCHEMA, play_inputs, verify_input_gameplay,
)


def _game() -> Campaign:
    path = Path(__file__).resolve().parents[1] / "game/gameplay/content/lantern_harbor.json"
    return Campaign.load(json.loads(path.read_text(encoding="utf-8")))


def _profile() -> InputProfile:
    path = Path(__file__).resolve().parents[1] / "game/presentation/fixtures/original_campaign_controls.json"
    return InputProfile.load(json.loads(path.read_text(encoding="utf-8")))


def _event(index: int, control: str, pressed: bool = True) -> dict:
    return {
        "event_id": f"e{index}", "sequence": index,
        "device_class": "keyboard", "control_path": control,
        "modifiers": [], "pressed": pressed,
    }


def test_keyboard_move_changes_real_game_and_replays() -> None:
    game, profile = _game(), _profile()
    result = play_inputs(game, profile, [_event(0, "KeyD")])
    assert result["schema_version"] == SCHEMA
    assert result["game_snapshot"]["state"]["x"] == 2
    assert result["transitions"][0]["game_command"]["kind"] == "move"
    assert Session.restore(game, result["game_snapshot"]).state_digest == result["game_state_digest"]
    assert verify_input_gameplay(game, profile, json.loads(json.dumps(result))) == result


def test_release_event_is_not_an_extra_game_move() -> None:
    result = play_inputs(_game(), _profile(), [
        _event(0, "KeyD"), _event(1, "KeyD", False),
    ])
    assert result["game_snapshot"]["state"]["x"] == 2
    assert result["game_snapshot"]["state"]["tick"] == 1
    assert result["transitions"][1]["game_command"] is None


def test_wall_collision_denied_atomically() -> None:
    events = [_event(0, "KeyD"), _event(1, "KeyD"), _event(2, "KeyD")]
    with pytest.raises(GameplayContractError, match="collision"):
        play_inputs(_game(), _profile(), events)


def test_contextual_interaction_collects_only_real_item() -> None:
    raw = _profile().manifest()
    raw["bindings"].append({
        "binding_id": "keyboard-interact", "action_id": "interact",
        "device_class": "keyboard", "control_path": "KeyE",
        "modifiers": [],
    })
    profile = InputProfile.load(raw)
    result = play_inputs(_game(), profile, [
        _event(0, "KeyD"), _event(1, "KeyE"),
    ])
    assert "lantern" in result["game_snapshot"]["state"]["inventory"]
    assert verify_input_gameplay(_game(), profile, result) == result


def test_interaction_absent_fails_closed() -> None:
    raw = _profile().manifest()
    raw["bindings"].append({
        "binding_id": "keyboard-interact", "action_id": "interact",
        "device_class": "keyboard", "control_path": "KeyE",
        "modifiers": [],
    })
    with pytest.raises(GameplayContractError, match="interaction"):
        play_inputs(_game(), InputProfile.load(raw), [_event(0, "KeyE")])


def test_forged_game_state_rejected() -> None:
    result = play_inputs(_game(), _profile(), [_event(0, "KeyD")])
    result["game_snapshot"]["state"]["x"] = 8
    with pytest.raises(GameplayContractError):
        verify_input_gameplay(_game(), _profile(), result)


def test_profile_identity_change_rejected() -> None:
    result = play_inputs(_game(), _profile(), [_event(0, "KeyD")])
    raw = _profile().manifest()
    raw["revision"] = 1
    with pytest.raises(GameplayContractError, match="source"):
        verify_input_gameplay(_game(), InputProfile.load(raw), result)


def test_cli_gameplay_bridge_with_canonical_fixtures() -> None:
    root = Path(__file__).resolve().parents[1]
    profile = root / "game/presentation/fixtures/original_campaign_controls.json"
    game = root / "game/gameplay/content/lantern_harbor.json"
    events = Path(__file__).resolve().parent / "fixtures/input_bridge_moves.json"
    run = subprocess.run([
        sys.executable, "-m", "scripts.game.route_inputs",
        "--profile", str(profile), "--events", str(events),
        "--game-source", str(game),
    ], capture_output=True, text=True, check=False, timeout=15)
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["game_snapshot"]["state"]["x"] == 2
    assert verify_input_gameplay(_game(), _profile(), report) == report
