"""Source-bound forge play, combat, crafting, recovery and adversarial saves."""
import copy
import json

import pytest

from skeleton.game.gameplay.arena_forge_run import (
    SCHEMA, cli, export_forge, import_forge, new_forge, normalize_forge,
    original_forge, resume_forge, simulate_forge, verify_forge,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.tactical_arena import verify_arena

ACTIONS = [
    {"kind": "fight"},
    {"kind": "craft", "recipe_id": "tide_edge"},
    {"kind": "equip", "recipe_id": "tide_edge"},
    {"kind": "fight"},
]


def test_original_is_playable_with_earned_equipment():
    result = simulate_forge(original_forge(), ACTIONS)
    assert result["state"]["phase"] == "won"
    assert result["state"]["next_index"] == 2
    assert result["state"]["materials"] == {"tide_iron": 1}
    assert result["state"]["gear"]["tide_edge"] == 1
    assert result["state"]["fights"][1]["equipped"] == "tide_edge"
    for fight in result["state"]["fights"]:
        assert verify_arena(fight["combat"]) == fight["combat"]
    assert verify_forge(json.loads(json.dumps(result))) == result


def test_resume_equals_uninterrupted_and_bundle_round_trip():
    first = simulate_forge(original_forge(), ACTIONS[:1])
    full = simulate_forge(original_forge(), ACTIONS)
    assert resume_forge(json.loads(json.dumps(first)), ACTIONS[1:]) == full
    assert import_forge(json.loads(json.dumps(export_forge(full)))) == full


def test_earned_materials_and_gear_cannot_be_forged():
    with pytest.raises(CombatSessionError, match="insufficient"):
        simulate_forge(original_forge(), [ACTIONS[1]])
    with pytest.raises(CombatSessionError, match="not owned"):
        simulate_forge(original_forge(), [ACTIONS[2]])
    with pytest.raises(CombatSessionError, match="already owned"):
        simulate_forge(original_forge(), ACTIONS[:2] + [ACTIONS[1]])


def test_unequip_and_reequip_are_replayable():
    actions = ACTIONS[:3] + [{"kind": "unequip"}] + ACTIONS[2:]
    assert simulate_forge(original_forge(), actions)["state"]["phase"] == "won"


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(schema_version="future"),
    lambda x: x["stages"][0]["arena"].update(world_id="other"),
    lambda x: x["stages"][1]["arena"].update(arena_id="lantern_salvage"),
    lambda x: x["stages"][1]["arena"]["actors"][0].update(attack=99),
    lambda x: x["stages"][0]["drops"][0].update(quantity=True),
    lambda x: x["stages"][0]["drops"].append(x["stages"][0]["drops"][0]),
    lambda x: x["recipes"][0].update(durability=0),
    lambda x: x["recipes"][0].update(attack_bonus=1001),
    lambda x: x["recipes"][0].update(costs=[{"id": "unearned", "quantity": 1}]),
    lambda x: x["recipes"][0].update(attack_bonus=0, defense_bonus=0),
])
def test_invalid_authored_sources_fail_closed(mutate):
    source = original_forge()
    mutate(source)
    with pytest.raises(CombatSessionError):
        normalize_forge(source)


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"].update(hero_hp=10000),
    lambda x: x["state"]["materials"].update(tide_iron=999),
    lambda x: x["state"]["gear"].update(tide_edge=999),
    lambda x: x["state"]["fights"][0].update(victory=False),
    lambda x: x["state"]["fights"][0]["combat"]["state"].update(winner="forged"),
    lambda x: x["journal"][1]["action"].update(recipe_id="other"),
    lambda x: x["journal"][1].update(receipt="0" * 64),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x.update(event_bus_digest="0" * 64),
])
def test_mutated_saves_never_grant_progress(mutate):
    session = copy.deepcopy(simulate_forge(original_forge(), ACTIONS))
    mutate(session)
    with pytest.raises(CombatSessionError):
        verify_forge(session)


def test_rejected_action_leaves_prior_checkpoint_unchanged():
    session = new_forge(original_forge())
    with pytest.raises(CombatSessionError):
        resume_forge(session, [ACTIONS[2]])
    assert session["state"]["tick"] == 0
    assert session["journal"] == []


def test_cli_demo_preview_and_errors(capsys):
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["phase"] == "won"
    assert cli(["preview", "--source-json", json.dumps(original_forge())]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == SCHEMA
    assert cli(["preview", "--source-json", "{}"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
