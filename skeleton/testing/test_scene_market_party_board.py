"""Legal party board is non-mutating and canonical-action verified."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market_party import (
    _advance, new_party, original_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_board import inspect_party
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_initial_board_is_nonmutating_and_role_filtered():
    source, _ = original_party()
    session = new_party(source)
    original = copy.deepcopy(session)
    board = inspect_party(session)
    assert session == original
    assert board["player_id"] == "rowan"
    assert {"kind": "pass"} in board["legal_actions"]
    assert all(action["kind"] in ("pass", "tile", "buy")
               for action in board["legal_actions"])
    assert board["credits"] == 0
    for action in board["legal_actions"]:
        assert _advance(session, {"player_id": "rowan", "action": action})


def test_role_rotation_filters_artisan_and_courier():
    source, _ = original_party()
    session = _advance(new_party(source), {
        "player_id": "rowan", "action": {"kind": "pass"}})
    board = inspect_party(session)
    assert board["player_id"] == "mira"
    assert all(action["kind"] in ("pass", "tile", "craft")
               for action in board["legal_actions"])


def test_terminal_board_is_empty_and_replay_derived():
    source, turns = original_party()
    terminal = simulate_party(source, turns)
    board = inspect_party(terminal)
    assert board["phase"] == "won"
    assert board["legal_actions"] == []


def test_forged_state_is_not_a_hint_source():
    source, turns = original_party()
    checkpoint = simulate_party(source, turns[:3])
    checkpoint["state"]["market"]["state"]["credits"] = 999
    with pytest.raises(SceneTravelError):
        inspect_party(checkpoint)


def test_board_cli_is_user_reachable(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-board", "demo"]) == 0
    board = json.loads(capsys.readouterr().out)
    assert board["legal_actions"]
    assert main(["scene-market-party-board", "terminal"]) == 0
    board = json.loads(capsys.readouterr().out)
    assert board["legal_actions"] == []
