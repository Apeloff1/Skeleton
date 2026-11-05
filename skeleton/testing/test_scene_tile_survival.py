"""Deterministic tile survival, earned food, hazards and replay integrity."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_tile_survival import (
    _advance, cli, export_survival, import_survival, new_survival,
    normalize_survival, original_survival, resume_survival, simulate_survival,
    verify_survival,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def demo():
    return original_survival()


def test_original_survival_is_playable_and_portable(demo):
    source, actions = demo
    saved = simulate_survival(source, actions)
    assert saved["state"]["phase"] == "won"
    assert saved["state"]["health"] == 3
    assert saved["state"]["food"] == 0
    assert saved["state"]["tile"]["state"]["scene"]["state"]["inventory"] == [
        "brass_key"
    ]
    assert verify_survival(json.loads(json.dumps(saved))) == saved
    assert import_survival(export_survival(saved)) == saved


@pytest.mark.parametrize("split", [0, 1, 2, 3, 5, 6, 8, 9])
def test_checkpoint_resume_matches_full_replay(demo, split):
    source, actions = demo
    part = simulate_survival(source, actions[:split])
    assert resume_survival(json.loads(json.dumps(part)), actions[split:]) == (
        simulate_survival(source, actions)
    )


def test_hazard_damage_and_earned_food(demo):
    source, actions = demo
    start = new_survival(source)
    assert start["state"]["food"] == 0
    after_collect = simulate_survival(source, actions[:2])
    assert after_collect["state"]["food"] == 1
    wounded = simulate_survival(source, actions[:3])
    assert wounded["state"]["health"] == 2
    assert wounded["state"]["food"] == 1


def test_rest_requires_position_food_and_missing_health(demo):
    source, actions = demo
    with pytest.raises(SceneTravelError, match="unused camp"):
        _advance(new_survival(source), {"kind": "rest"})
    camp = simulate_survival(source, actions[:5])
    assert camp["state"]["health"] == 2
    healed = _advance(camp, {"kind": "rest"})
    assert healed["state"]["health"] == 3
    assert healed["state"]["food"] == 0
    with pytest.raises(SceneTravelError, match="unused camp"):
        _advance(healed, {"kind": "rest"})


def test_terminal_hazard_fails_closed(demo):
    source, actions = demo
    source["max_health"] = 1
    dead = simulate_survival(source, actions[:3])
    assert dead["state"]["phase"] == "lost"
    with pytest.raises(SceneTravelError, match="terminal"):
        _advance(dead, actions[3])


@pytest.mark.parametrize("mutation", [
    lambda x: x["hazards"].append(copy.deepcopy(x["hazards"][0])),
    lambda x: x["hazards"][0].update(at=[1, 0]),
    lambda x: x["hazards"][0].update(damage=True),
    lambda x: x["camps"][0].update(scene_id="unknown"),
    lambda x: x["camps"][0].update(at=[99, 99]),
    lambda x: x["food_pickups"].append("quay:find_key"),
    lambda x: x["food_pickups"].append("quay:free_food"),
    lambda x: x.update(initial_food=100),
    lambda x: x.update(turn_limit=0),
    lambda x: x.update(schema_version="future"),
])
def test_bad_sources_rejected(demo, mutation):
    source, _ = demo
    bad = copy.deepcopy(source)
    mutation(bad)
    with pytest.raises(SceneTravelError):
        normalize_survival(bad)


@pytest.mark.parametrize("mutation", [
    lambda x: x["state"].update(health=100),
    lambda x: x["state"].update(food=100),
    lambda x: x["state"]["tile"]["state"].update(position=[0, 0]),
    lambda x: x["journal"][0]["action"].update(kind="rest"),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x.update(source_digest="0" * 64),
])
def test_forged_saves_rejected(demo, mutation):
    source, actions = demo
    bad = copy.deepcopy(simulate_survival(source, actions))
    mutation(bad)
    with pytest.raises(SceneTravelError):
        verify_survival(bad)


def test_bundle_tampering_rejected(demo):
    source, actions = demo
    bundle = export_survival(simulate_survival(source, actions))
    for key in ("checksum", "source_digest", "state_digest"):
        bad = copy.deepcopy(bundle)
        bad[key] = "0" * 64
        with pytest.raises(SceneTravelError):
            import_survival(bad)


def test_canonical_cli_round_trip(capsys):
    from skeleton.__main__ import main
    assert main(["scene-survival", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["phase"] == "won"
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"x":1,"x":2}',
                "--actions-json", "[]"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_invalid_actions_and_turn_limit(demo):
    source, actions = demo
    source["turn_limit"] = 2
    saved = simulate_survival(source, actions[:2])
    assert saved["state"]["phase"] == "draw"
    with pytest.raises(SceneTravelError, match="terminal"):
        _advance(saved, actions[2])
    with pytest.raises(SceneTravelError):
        _advance(new_survival(source), {"kind": "tile", "action": {"kind": "fly"}})
