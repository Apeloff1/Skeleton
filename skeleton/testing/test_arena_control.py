"""Canonical control-point source -> movement -> replay -> author -> export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import (
    SCHEMA, _advance_control, new_control, normalize_control, original_actions,
    original_control, package_control, play_control, resume_control,
    verify_control, verify_control_package,
)
from skeleton.game.gameplay.arena_control_author import (
    author_control, verify_authoring,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_beacons_are_reachable_and_terminal():
    source = original_control()
    game = play_control(source, original_actions())
    assert game["state"]["phase"] == "won"
    assert game["state"]["winner"] == "wayfarers"
    assert game["state"]["scores"] == {"reedbound": 1, "wayfarers": 2}
    assert [x["zone_id"] for x in game["state"]["captures"]] == [
        "west_beacon", "east_beacon", "west_beacon",
    ]
    assert verify_control(json.loads(json.dumps(game))) == game
    assert game["arena_session"]["state"]["tick"] == 3
    assert game["state_digest"] == dig(game["state"])


def test_checkpoint_resume_matches_full_replay_and_is_immutable():
    source = original_control()
    actions = original_actions()
    initial = new_control(source)
    first = resume_control(initial, actions[:1])
    first_before = copy.deepcopy(first)
    second = resume_control(first, actions[1:])
    assert second == play_control(source, actions)
    assert first == first_before
    assert first["save"]["parent_save_digest"] == dig(initial["save"])
    assert second["save"]["parent_save_digest"] is not None
    with pytest.raises(CombatSessionError, match="terminal"):
        resume_control(second, actions[:1])


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"]["scores"].update(wayfarers=999),
    lambda x: x["arena_session"]["state"]["actors"]["scout"].update(hp=999),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["journal"][0]["captures"].clear(),
    lambda x: x["state"]["captures"].clear(),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(event_bus_digest="0" * 64),
])
def test_all_save_and_capture_tampering_is_rejected(mutate):
    session = play_control(original_control(), original_actions())
    corrupted = copy.deepcopy(session)
    mutate(corrupted)
    with pytest.raises(CombatSessionError):
        verify_control(corrupted)


@pytest.mark.parametrize("mutate", [
    lambda x: x["zones"][0].update(position=[3, 0]),
    lambda x: x["zones"][0].update(position=[32, 0]),
    lambda x: x["zones"][1].update(id="west_beacon"),
    lambda x: x["zones"][1].update(position=[1, 1]),
    lambda x: x.update(score_target=True),
    lambda x: x.update(max_actions=25),
    lambda x: x["zones"][0].update(points=0),
    lambda x: x["zones"].append(copy.deepcopy(x["zones"][0])),
    lambda x: x.update(schema_version="future"),
    lambda x: x.update(unknown="injection"),
])
def test_invalid_authoring_sources_fail_closed(mutate):
    source = original_control()
    mutate(source)
    with pytest.raises(CombatSessionError):
        normalize_control(source)


def test_invalid_tactical_moves_and_turn_order_do_not_advance_score():
    first = new_control(original_control())
    with pytest.raises(CombatSessionError, match="out-of-turn"):
        _advance_control(first, {"kind": "guard", "actor_id": "warden"})
    with pytest.raises(CombatSessionError, match="range"):
        _advance_control(first, {
            "kind": "attack", "actor_id": "scout", "target_id": "warden",
        })
    assert first["state"]["tick"] == 0
    assert first["state"]["scores"] == {"reedbound": 0, "wayfarers": 0}


def test_score_target_and_action_budget_have_deterministic_endings():
    source = original_control()
    source["score_target"] = 1
    win = play_control(source, original_actions()[:1])
    assert win["state"]["phase"] == "won"
    assert win["state"]["winner"] == "wayfarers"
    source = original_control()
    source["score_target"] = 200
    source["max_actions"] = 1
    draw = play_control(source, original_actions()[:1])
    assert draw["state"]["phase"] == "draw"
    assert draw["state"]["winner"] is None
    assert verify_control(draw) == draw


def test_portable_package_checks_canonical_arena_and_receipts():
    game = play_control(original_control(), original_actions())
    package = package_control(game)
    assert package["manifest"]["winner"] == "wayfarers"
    assert verify_control_package(json.loads(json.dumps(package))) == package
    bad = copy.deepcopy(package)
    bad["manifest"]["scores"]["wayfarers"] += 10
    with pytest.raises(CombatSessionError):
        verify_control_package(bad)
    bad = copy.deepcopy(package)
    bad["snapshot"]["source"]["score_target"] = 1
    with pytest.raises(CombatSessionError):
        verify_control_package(bad)


def test_authoring_is_atomic_source_fenced_and_preview_replayable():
    source = original_control()
    original = copy.deepcopy(source)
    operations = [
        {"kind": "set-score-target", "value": 1},
        {"kind": "set-zone-points", "zone_id": "west_beacon", "value": 2},
    ]
    receipt = author_control(source, operations, dig(normalize_control(source)),
                             original_actions()[:1])
    assert source == original
    assert receipt["preview"]["state"]["winner"] == "wayfarers"
    assert verify_authoring(source, receipt) == receipt
    bad = copy.deepcopy(receipt)
    bad["preview"]["state"]["scores"]["wayfarers"] = 1000
    with pytest.raises(CombatSessionError):
        verify_authoring(source, bad)
    with pytest.raises(CombatSessionError, match="stale"):
        author_control(source, operations, "0" * 64, original_actions()[:1])
    with pytest.raises(CombatSessionError, match="no-op"):
        author_control(source, [{"kind": "set-score-target", "value": 2}],
                       dig(normalize_control(source)), original_actions()[:1])


def test_source_to_runtime_to_portable_export_through_installed_cli(capsys):
    assert main(["arena-control-author", "demo"]) == 0
    edited = json.loads(capsys.readouterr().out)
    assert main([
        "arena-control-author", "verify",
        "--source-json", json.dumps(original_control()),
        "--receipt-json", json.dumps(edited),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == edited
    assert main([
        "arena-control", "play",
        "--source-json", json.dumps(edited["source"]),
        "--actions-json", json.dumps(edited["preview_actions"]),
    ]) == 0
    game = json.loads(capsys.readouterr().out)
    assert game == edited["preview"]
    assert main([
        "arena-control", "pack", "--session-json", json.dumps(game),
    ]) == 0
    portable = json.loads(capsys.readouterr().out)
    assert main([
        "arena-control", "unpack", "--package-json", json.dumps(portable),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == portable
    assert main([
        "arena-control", "verify", "--session-json", json.dumps(game),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == game


def test_cli_invalid_action_fails_closed(capsys):
    assert main([
        "arena-control", "play",
        "--source-json", json.dumps(original_control()),
        "--actions-json", json.dumps([{"kind": "teleport", "actor_id": "scout"}]),
    ]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
