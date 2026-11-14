"""B024 historical device control → canonical offline playable source/replay."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import GameplayContractError
from skeleton.game.gameplay.offline_grid_campaign import Campaign, Session
from skeleton.game.presentation.input_actions import Control, InputContractError, InputState
from skeleton.game.presentation.genre_action_profiles import genre_action_map
from skeleton.game.presentation.genre_playable_adapter import (
    play_genre_campaign, playable_input_profile, verify_genre_campaign,
)


def game() -> Campaign:
    path = Path(__file__).resolve().parents[1] / "game/gameplay/content/lantern_harbor.json"
    return Campaign.load(json.loads(path.read_text(encoding="utf-8")))


def event(index, device, path, pressed=True, modifiers=()):
    return {
        "event_id": f"g{index}", "sequence": index, "device_class": device,
        "control_path": path, "modifiers": list(modifiers), "pressed": pressed,
    }


def test_real_rpg_keyboard_controls_move_and_collect_in_current_game_runtime():
    state = InputState(genre_action_map("rpg"))
    state.feed("keyboard:key.d", 1)
    state.update()
    assert state.value("move") == (1.0, 0.0)
    p = playable_input_profile("rpg")
    assert "move-east" in {b["action_id"] for b in p.manifest()["bindings"]}
    report = play_genre_campaign(game(), "rpg", [
        event(0, "keyboard", "key.d"),
        event(1, "keyboard", "key.e"),
    ])
    g = report["gameplay"]
    assert g["game_snapshot"]["state"]["x"] == 2
    assert "lantern" in g["game_snapshot"]["state"]["inventory"]
    assert Session.restore(game(), g["game_snapshot"]).state_digest == g["game_state_digest"]
    assert verify_genre_campaign(game(), json.loads(json.dumps(report))) == report


def test_gamepad_dpad_and_touch_share_exact_semantic_gameplay():
    m = genre_action_map("rpg")
    s = InputState(m)
    s.feed("gamepad:button.dpad_right", 1)
    s.update()
    assert s.value("move") == (1.0, 0.0)
    profile = playable_input_profile("rpg")
    assert any(b.device_class == "controller" and b.control_path == "button.dpad_right"
               for b in profile.bindings)
    report = play_genre_campaign(game(), "rpg", [
        event(0, "controller", "button.dpad_right"),
        event(1, "touch", "long_press"),
    ])
    assert "lantern" in report["gameplay"]["game_snapshot"]["state"]["inventory"]
    assert verify_genre_campaign(game(), report) == report


def test_remapped_keyboard_chord_changes_real_profile_digest_and_replay():
    original = playable_input_profile("rpg")
    scheme = genre_action_map("rpg")
    scheme.rebind("move", Control.parse("keyboard:key.d"), Control.parse("keyboard:key.l"))
    overrides = scheme.export_overrides()
    updated = playable_input_profile("rpg", overrides)
    assert original.digest != updated.digest
    report = play_genre_campaign(game(), "rpg", [event(0, "keyboard", "key.l")], overrides=overrides)
    assert report["gameplay"]["game_snapshot"]["state"]["x"] == 2
    assert verify_genre_campaign(game(), report) == report
    with pytest.raises(GameplayContractError):
        forged = deepcopy(report)
        forged["overrides"] = {}
        forged["digest"] = report["digest"]
        verify_genre_campaign(game(), forged)


def test_tampering_with_a_real_game_progress_or_profile_is_rejected():
    original = play_genre_campaign(game(), "rpg", [event(0, "keyboard", "key.d")])
    forged = deepcopy(original)
    forged["gameplay"]["game_snapshot"]["state"]["x"] = 8
    with pytest.raises(GameplayContractError):
        verify_genre_campaign(game(), forged)
    forged = deepcopy(original)
    forged["profile"]["revision"] = 123
    with pytest.raises(GameplayContractError):
        verify_genre_campaign(game(), forged)


def test_racing_analog_controls_are_not_misrepresented_as_grid_game_movement():
    with pytest.raises(InputContractError, match="no compatible discrete"):
        playable_input_profile("racing")


def test_unknown_genres_and_conflicting_binding_overrides_fail_closed():
    with pytest.raises(InputContractError):
        playable_input_profile("../mystery")
    with pytest.raises(InputContractError):
        playable_input_profile("rpg", {
            "move": [{"control": "keyboard:key.e", "modifiers": [], "scale": 1.0,
                      "axis": "x", "deadzone": 0.0}]
        })


def test_noncanonical_override_payload_rejected_even_with_recomputed_digest():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    good = play_genre_campaign(game(), "rpg", [event(0, "keyboard", "key.d")])
    forged = deepcopy(good)
    forged["overrides"] = {"move": []}
    forged["digest"] = dig({k: v for k, v in forged.items() if k != "digest"})
    with pytest.raises(GameplayContractError):
        verify_genre_campaign(game(), forged)
