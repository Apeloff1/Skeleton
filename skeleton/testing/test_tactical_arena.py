"""Real offline arena: movement, combat, replay, deterministic AI and CLI."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.tactical_arena import (
    SCHEMA, _advance, cli, legal_moves, legal_targets, new_arena,
    normalize_arena, original_arena, resume_arena, simulate_arena,
    verify_arena,
)
from skeleton.game.gameplay.arena_policy import choose_action, run_autoplay


def action(kind, actor_id, **rest):
    return {"kind": kind, "actor_id": actor_id, **rest}


def test_original_arena_has_real_playable_offline_completion():
    source = original_arena()
    finished = run_autoplay(source)
    assert finished["state"]["phase"] in ("won", "draw")
    assert 1 <= len(finished["journal"]) <= source["turn_limit"]
    assert verify_arena(json.loads(json.dumps(finished))) == finished
    assert finished["source_digest"] == new_arena(source)["source_digest"]
    assert all(e["receipt"] for e in finished["journal"])


def test_collision_turn_order_and_orthogonal_visibility():
    source = original_arena()
    session = new_arena(source)
    assert legal_targets(session["source"], session["state"], "scout") == []
    assert "east" in legal_moves(session["source"], session["state"], "scout")
    with pytest.raises(CombatSessionError, match="out-of-turn"):
        _advance(session, action("move", "warden", direction="west"))
    with pytest.raises(CombatSessionError, match="range"):
        _advance(session, action("attack", "scout", target_id="warden"))
    moved = _advance(session, action("move", "scout", direction="east"))
    assert moved["state"]["actors"]["scout"]["position"] == [1, 1]
    assert session["state"]["actors"]["scout"]["position"] == [0, 1]
    assert moved["save"]["parent_save_digest"]
    with pytest.raises(CombatSessionError, match="out-of-turn"):
        _advance(moved, action("move", "scout", direction="east"))


def test_replay_prefix_resume_is_bit_identical():
    source = original_arena()
    first = _advance(new_arena(source), action("move", "scout", direction="east"))
    second = _advance(first, action("move", "warden", direction="west"))
    resumed = resume_arena(json.loads(json.dumps(first)), [
        action("move", "warden", direction="west"),
    ])
    assert resumed == second
    assert verify_arena(second) == second
    assert len(second["journal"]) == 2
    assert second["event_bus_digest"] != first["event_bus_digest"]


def test_guard_and_rest_are_real_state_transitions():
    source = original_arena()
    first = _advance(new_arena(source), action("guard", "scout"))
    assert first["state"]["actors"]["scout"]["guard"] is True
    second = _advance(first, action("rest", "warden"))
    assert second["state"]["tick"] == 2
    assert verify_arena(second) == second


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(width=True),
    lambda x: x.update(width=33),
    lambda x: x.update(turn_limit=257),
    lambda x: x["walls"].append(x["walls"][0]),
    lambda x: x["actors"][0].update(position=[3, 0]),
    lambda x: x["actors"][1].update(position=[0, 1]),
    lambda x: x["actors"][0].update(range=0),
    lambda x: x["actors"][0].update(max_hp=0),
    lambda x: x["actors"][0].update(team="reedbound"),
    lambda x: x["actors"][0].update(unknown="forged"),
    lambda x: x.update(schema_version="future"),
])
def test_invalid_authored_sources_fail_closed(mutation):
    source = original_arena()
    mutation(source)
    with pytest.raises(CombatSessionError):
        normalize_arena(source)


@pytest.mark.parametrize("mutation", [
    lambda x: x["state"]["actors"]["scout"].update(hp=999),
    lambda x: x["state"].update(tick=99),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="f" * 64),
    lambda x: x.update(event_bus_digest="0" * 64),
    lambda x: x["journal"].append(x["journal"][0]),
])
def test_tampered_save_and_journal_rejected(mutation):
    source = original_arena()
    session = _advance(new_arena(source), action("move", "scout", direction="east"))
    bad = copy.deepcopy(session)
    mutation(bad)
    with pytest.raises(CombatSessionError):
        verify_arena(bad)


def test_wall_and_living_actor_block_ray():
    source = original_arena()
    source["actors"][0]["position"] = [3, 0]
    with pytest.raises(CombatSessionError, match="blocked"):
        normalize_arena(source)
    source = original_arena()
    source["actors"][0]["position"] = [1, 1]
    source["actors"][0]["range"] = 8
    source["actors"][1]["position"] = [5, 1]
    session = new_arena(source)
    assert legal_targets(session["source"], session["state"], "scout") == ["warden"]
    source["walls"].append([3, 1])
    session = new_arena(source)
    assert legal_targets(session["source"], session["state"], "scout") == []


def test_source_mismatch_cannot_rebind_autoplay_checkpoint():
    source = original_arena()
    checkpoint = _advance(new_arena(source), action("guard", "scout"))
    altered = copy.deepcopy(source)
    altered["actors"][0]["attack"] += 1
    with pytest.raises(CombatSessionError, match="source mismatch"):
        run_autoplay(altered, resume=checkpoint)


def test_autoplay_is_stable_and_policy_replays_from_verified_state():
    source = original_arena()
    session = new_arena(source)
    assert choose_action(session) == choose_action(copy.deepcopy(session))
    assert run_autoplay(source) == run_autoplay(copy.deepcopy(source))
    with pytest.raises(CombatSessionError):
        choose_action({"state": {"tick": 0}})


def test_cli_demo_and_exported_save_verification(capsys):
    assert cli(["demo"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["schema_version"] == SCHEMA
    assert cli(["verify", "--session-json", json.dumps(session)]) == 0
    assert json.loads(capsys.readouterr().out) == session
    assert cli(["simulate", "--source-json", json.dumps(original_arena()),
                "--actions-json", json.dumps([action("move", "scout", direction="east")])]) == 0
    checkpoint = json.loads(capsys.readouterr().out)
    assert checkpoint["state"]["tick"] == 1
    assert cli(["resume", "--session-json", json.dumps(checkpoint),
                "--actions-json", json.dumps([action("guard", "warden")])]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["tick"] == 2


def test_cli_bad_inputs_never_report_success(capsys):
    assert cli(["simulate", "--source-json", '{"broken":true}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert cli(["verify", "--session-json", '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
    assert cli(["simulate", "--source-json", json.dumps(original_arena()),
                "--actions-json", json.dumps([action("teleport", "scout")])]) == 2


def test_main_cli_reaches_canonical_arena(capsys):
    from skeleton.__main__ import main
    assert main(["combat-arena", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == SCHEMA
