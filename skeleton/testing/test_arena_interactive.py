"""Interactive accessible arena and bounded source-bound tactical routing."""
from __future__ import annotations

import copy
import io
import json
import pytest

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.tactical_arena import (
    _advance, cli, new_arena, original_arena, verify_arena,
)
from skeleton.game.gameplay.arena_interactive import play_arena, render_arena
from skeleton.game.gameplay.arena_routes import route_to_attack
from skeleton.game.gameplay.arena_policy import choose_action, run_autoplay


def act(kind, actor, **kwargs):
    return {"kind": kind, "actor_id": actor, **kwargs}


def test_map_is_stable_and_screen_reader_accessible():
    session = new_arena(original_arena())
    frame = render_arena(session["source"], session["state"])
    assert frame["rows"] == ["...#...", "0.....1", "...#..."]
    assert [x["id"] for x in frame["legend"]] == ["scout", "warden"]
    assert frame["legend"][0]["hp"] == 14


def test_interactive_two_turn_draw_and_verified_export():
    source = original_arena()
    source["turn_limit"] = 2
    reader = io.StringIO(
        json.dumps(act("guard", "scout")) + "\n"
        + json.dumps(act("guard", "warden")) + "\n"
    )
    writer = io.StringIO()
    result = play_arena(source, input_stream=reader, output_stream=writer)
    events = [json.loads(x) for x in writer.getvalue().splitlines()]
    assert [e["event"] for e in events] == ["turn", "turn", "terminal"]
    assert events[0]["legal_moves"] == ["north", "east", "south"]
    assert events[-1]["session"] == result
    assert result["state"]["phase"] == "draw"
    assert verify_arena(result) == result


def test_invalid_human_action_is_retried_without_mutation():
    source = original_arena()
    source["turn_limit"] = 1
    reader = io.StringIO(
        '{"kind":"teleport","actor_id":"scout"}\n'
        + json.dumps(act("guard", "scout")) + "\n"
    )
    writer = io.StringIO()
    result = play_arena(source, input_stream=reader, output_stream=writer)
    events = [json.loads(x) for x in writer.getvalue().splitlines()]
    assert [e["event"] for e in events] == [
        "turn", "rejected", "terminal"
    ]
    assert result["state"]["tick"] == 1
    assert events[1]["remaining_retries"] == 2


def test_eof_and_three_invalid_inputs_do_not_fabricate_terminal():
    source = original_arena()
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="input ended"):
        play_arena(source, input_stream=io.StringIO(""),
                   output_stream=writer)
    assert "terminal" not in writer.getvalue()
    bad = '{"kind":"teleport","actor_id":"scout"}\n' * 3
    writer = io.StringIO()
    with pytest.raises(CombatSessionError, match="three invalid"):
        play_arena(source, input_stream=io.StringIO(bad),
                   output_stream=writer)
    assert "terminal" not in writer.getvalue()


def test_automated_opponents_keep_human_turns_and_valid_receipts():
    source = original_arena()
    source["turn_limit"] = 2
    writer = io.StringIO()
    result = play_arena(
        source, input_stream=io.StringIO(json.dumps(act("guard", "scout")) + "\n"),
        output_stream=writer, auto_teams=["reedbound"],
    )
    events = [json.loads(x) for x in writer.getvalue().splitlines()]
    assert [e["event"] for e in events] == [
        "turn", "auto_action", "terminal"
    ]
    assert verify_arena(result) == result
    assert events[1]["receipt"] == result["journal"][-1]["receipt"]


@pytest.mark.parametrize("auto", [
    ["reedbound", "reedbound"], ["missing"], ["reedbound", "wayfarers"],
    "reedbound", [False],
])
def test_invalid_automation_identity_is_rejected(auto):
    with pytest.raises(CombatSessionError):
        play_arena(original_arena(), auto_teams=auto,
                   input_stream=io.StringIO(""))


def test_interactive_resume_requires_exact_authored_source():
    source = original_arena()
    checkpoint = _advance(new_arena(source), act("guard", "scout"))
    changed = copy.deepcopy(source)
    changed["actors"][0]["attack"] += 1
    with pytest.raises(CombatSessionError, match="source mismatch"):
        play_arena(changed, resume=checkpoint, input_stream=io.StringIO(""))


def test_route_avoids_wall_and_reaches_attack_position():
    source = original_arena()
    source["walls"] = [[2, 1]]
    session = new_arena(source)
    route = route_to_attack(session)
    assert route["reachable"] is True
    assert route["moves"]
    assert route["source_digest"] == session["source_digest"]
    assert route["moves"][0] in ("north", "south")
    for direction in route["moves"]:
        actor = "scout" if session["state"]["tick"] % 2 == 0 else "warden"
        if actor == "scout":
            session = _advance(session, act("move", actor, direction=direction))
        else:
            session = _advance(session, act("guard", actor))
            session = _advance(session, act("move", "scout", direction=direction))
    assert route_to_attack(session)["moves"] == []


def test_unreachable_route_returns_none_without_fake_path():
    source = original_arena()
    source["walls"] = [[1, 0], [1, 1], [1, 2]]
    session = new_arena(source)
    route = route_to_attack(session)
    assert route["reachable"] is False
    assert route["moves"] is None
    assert choose_action(session)["kind"] == "guard"


def test_policy_uses_reachable_route_and_replay_stable():
    source = original_arena()
    source["walls"] = [[2, 1]]
    session = new_arena(source)
    first = choose_action(session)
    assert first["kind"] == "move"
    assert first["direction"] in ("north", "south")
    assert run_autoplay(source) == run_autoplay(copy.deepcopy(source))


def test_bad_action_kind_list_rejected_as_domain_error():
    session = new_arena(original_arena())
    with pytest.raises(CombatSessionError, match="unsupported"):
        _advance(session, {"kind": [], "actor_id": "scout"})


def test_cli_interactive_mode_uses_real_engine(monkeypatch, capsys):
    import sys
    source = original_arena()
    source["turn_limit"] = 1
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        json.dumps(act("guard", "scout")) + "\n"
    ))
    assert cli(["play", "--source-json", json.dumps(source)]) == 0
    events = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert events[-1]["event"] == "terminal"
    assert events[-1]["session"]["state"]["phase"] == "draw"
