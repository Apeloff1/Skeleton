"""Forge source editor: atomic updates, real playable preview, replay receipt."""
import copy
import json

import pytest

from skeleton.game.gameplay.arena_forge_author import (
    SCHEMA, author_forge, cli, verify_author_report,
)
from skeleton.game.gameplay.arena_forge_run import original_forge
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_atomic_recipe_edit_and_replayable_preview():
    source = original_forge()
    report = author_forge(source, [{
        "kind": "set_recipe", "recipe_id": "tide_edge",
        "attack_bonus": 6, "defense_bonus": 1, "durability": 2,
    }])
    assert report["source"]["recipes"][0]["attack_bonus"] == 6
    assert source["recipes"][0]["attack_bonus"] == 5
    assert report["preview"]["status"] == "found"
    assert verify_author_report(json.loads(json.dumps(report))) == report


def test_add_recipe_then_rebalance_drops():
    source = original_forge()
    report = author_forge(source, [{
        "kind": "add_recipe", "recipe": {
            "id": "guard_plate", "costs": [{"id": "tide_iron", "quantity": 1}],
            "attack_bonus": 0, "defense_bonus": 4, "durability": 2,
        },
    }, {
        "kind": "set_drops", "arena_id": "lantern_salvage",
        "drops": [{"id": "tide_iron", "quantity": 3}],
    }])
    assert len(report["source"]["recipes"]) == 2
    assert report["source"]["stages"][0]["drops"][0]["quantity"] == 3


@pytest.mark.parametrize("edits", [
    [{"kind": "remove_recipe", "recipe_id": "tide_edge"}],
    [{"kind": "set_recipe", "recipe_id": "tide_edge",
      "attack_bonus": 0, "defense_bonus": 0, "durability": 2}],
    [{"kind": "set_costs", "recipe_id": "tide_edge",
      "costs": [{"id": "unknown", "quantity": 1}]}],
    [{"kind": "set_drops", "arena_id": "missing", "drops": []}],
    [{"kind": "add_recipe", "recipe": {
        "id": "tide_edge", "costs": [{"id": "tide_iron", "quantity": 2}],
        "attack_bonus": 5, "defense_bonus": 1, "durability": 2,
    }}],
])
def test_invalid_edit_batch_does_not_mutate_source(edits):
    source = original_forge()
    original = copy.deepcopy(source)
    with pytest.raises(CombatSessionError):
        author_forge(source, edits)
    assert source == original


def test_tampered_report_cannot_certify():
    report = author_forge(original_forge(), [])
    report["preview"]["status"] = "unreachable"
    with pytest.raises(CombatSessionError):
        verify_author_report(report)


def test_cli_demo_and_invalid_input(capsys):
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == SCHEMA
    assert cli(["patch", "--source-json", "{}", "--edits-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
