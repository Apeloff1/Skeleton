"""ASCII capture board is a replay-derived view, not trusted state."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import (
    new_control, original_actions, original_control, play_control,
)
from skeleton.game.gameplay.arena_control_render import (
    render_control, verify_render,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_board_shows_real_walls_actors_zones_and_scores():
    session = play_control(original_control(), original_actions())
    view = render_control(session)
    assert view["phase"] == "won"
    assert view["scores"]["wayfarers"] == 2
    assert len(view["rows"]) == 3
    assert all(len(row) == 7 for row in view["rows"])
    assert view["rows"][0][3] == "#"
    assert view["rows"][2][3] == "#"
    assert view["ascii"] == "\n".join(view["rows"])
    assert view["actors"][0]["actor_id"] == "scout"
    assert view["zones"][0]["zone_id"] == "east_beacon"
    assert verify_render(session, json.loads(json.dumps(view))) == view


def test_render_is_deterministic_from_unchanged_source_and_checkpoint():
    session = new_control(original_control())
    view = render_control(session)
    assert render_control(copy.deepcopy(session)) == view
    assert view["phase"] == "active"
    assert view["tick"] == 0
    assert view["rows"][1][0] in "ABCDEFGHIJKLMNOP"


@pytest.mark.parametrize("mutate", [
    lambda x: x["rows"][0].replace(".", "X"),
    lambda x: x.update(ascii="forged"),
    lambda x: x["scores"].update(wayfarers=999),
    lambda x: x["actors"][0].update(hp=999),
    lambda x: x.update(receipt="0" * 64),
])
def test_edited_render_rejected(mutate):
    session = play_control(original_control(), original_actions())
    view = render_control(session)
    altered = copy.deepcopy(view)
    mutate(altered)
    if altered == view:
        altered["rows"][0] = "XXXXXXX"
    with pytest.raises(CombatSessionError):
        verify_render(session, altered)


def test_render_rejects_tampered_checkpoint():
    session = play_control(original_control(), original_actions())
    session["state"]["scores"]["wayfarers"] = 999
    with pytest.raises(CombatSessionError):
        render_control(session)


def test_installed_cli_render_and_verify(capsys):
    assert main(["arena-control-render", "demo"]) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["schema_version"] == "skeleton.arena_control_render.v1"
    session = play_control(original_control(), original_actions())
    assert main([
        "arena-control-render", "verify",
        "--session-json", json.dumps(session),
        "--render-json", json.dumps(view),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == view
