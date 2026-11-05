"""Canonical scene tile collision, pickup, locked exits and replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_tile_walk import (
    _advance, cli, export_tiles, import_tiles, new_tiles, normalize_tiles,
    original_tiles, resume_tiles, simulate_tiles, verify_tiles,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def demo():
    return original_tiles()


def test_original_tile_game_reaches_earned_victory(demo):
    source, actions = demo
    saved = simulate_tiles(source, actions)
    assert saved["state"]["phase"] == "won"
    assert saved["state"]["scene"]["state"]["inventory"] == ["brass_key"]
    assert saved["state"]["scene"]["state"]["scene_id"] == "sanctuary"
    assert verify_tiles(json.loads(json.dumps(saved))) == saved
    assert import_tiles(json.loads(json.dumps(export_tiles(saved)))) == saved


@pytest.mark.parametrize("split", [0, 1, 2, 4, 5, 7, 8])
def test_checkpoint_resume_matches_full_play(demo, split):
    source, actions = demo
    partial = simulate_tiles(source, actions[:split])
    assert resume_tiles(json.loads(json.dumps(partial)), actions[split:]) == (
        simulate_tiles(source, actions)
    )


def test_collision_and_wall_reject_without_mutation(demo):
    source, _ = demo
    start = new_tiles(source)
    with pytest.raises(SceneTravelError, match="collision"):
        _advance(start, {"kind": "move", "direction": "west"})
    north = _advance(start, {"kind": "move", "direction": "north"})
    with pytest.raises(SceneTravelError, match="collision"):
        _advance(north, {"kind": "move", "direction": "east"})
    assert start == new_tiles(source)


def test_pickup_and_exit_require_physical_position(demo):
    source, _ = demo
    start = new_tiles(source)
    with pytest.raises(SceneTravelError, match="position"):
        _advance(start, {"kind": "collect", "pickup_id": "find_key"})
    with pytest.raises(SceneTravelError, match="position"):
        _advance(start, {"kind": "travel", "exit_id": "north"})


def test_locked_exit_requires_earned_canonical_key(demo):
    source, _ = demo
    walk = simulate_tiles(source, [{"kind": "move", "direction": "east"}] * 3)
    with pytest.raises(SceneTravelError, match="requires"):
        _advance(walk, {"kind": "travel", "exit_id": "north"})


def test_original_failure_route_and_terminal_hold(demo):
    source, _ = demo
    lost = simulate_tiles(source, [
        {"kind": "move", "direction": "south"},
        {"kind": "travel", "exit_id": "down"},
    ])
    assert lost["state"]["phase"] == "lost"
    with pytest.raises(SceneTravelError, match="terminal"):
        _advance(lost, {"kind": "move", "direction": "east"})


@pytest.mark.parametrize("mutate", [
    lambda x: x["maps"][0]["walls"].append([1, 0]),
    lambda x: x["maps"][0]["walls"].append([0, 1]),
    lambda x: x["maps"][0]["pickups"][0].update(at=[1, 0]),
    lambda x: x["maps"][0]["exits"][0].update(id="unknown"),
    lambda x: x["maps"][0].update(width=True),
    lambda x: x["maps"][0].update(spawn=[99, 99]),
    lambda x: x["maps"].pop(),
    lambda x: x.update(schema_version="future"),
])
def test_bad_authored_tile_maps_fail_closed(demo, mutate):
    source, _ = demo
    bad = copy.deepcopy(source)
    mutate(bad)
    with pytest.raises(SceneTravelError):
        normalize_tiles(bad)


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"].update(position=[3, 1]),
    lambda x: x["state"]["scene"]["state"].update(inventory=["free"]),
    lambda x: x["journal"][0]["action"].update(direction="north"),
    lambda x: x["journal"][1].update(receipt="0" * 64),
    lambda x: x.update(source_digest="0" * 64),
])
def test_forged_tile_saves_rejected(demo, mutate):
    source, actions = demo
    bad = copy.deepcopy(simulate_tiles(source, actions))
    mutate(bad)
    with pytest.raises(SceneTravelError):
        verify_tiles(bad)


def test_bundle_tampering_rejected(demo):
    source, actions = demo
    bundle = export_tiles(simulate_tiles(source, actions))
    for key in ("checksum", "source_digest", "state_digest"):
        bad = copy.deepcopy(bundle)
        bad[key] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_tiles(bad)


def test_canonical_cli_demo_export_import(capsys):
    from skeleton.__main__ import main
    assert main(["scene-tiles", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_step_limit_and_invalid_action(demo):
    source, actions = demo
    source["step_limit"] = 2
    partial = simulate_tiles(source, actions[:2])
    with pytest.raises(SceneTravelError, match="budget"):
        resume_tiles(partial, actions[2:3])
    with pytest.raises(SceneTravelError):
        _advance(new_tiles(source), {"kind": "move", "direction": "teleport"})
