"""End-to-end canonical expedition quest, crafting, NPC and replay tests."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import (
    _advance, cli, demo_actions, export_quest, import_quest, new_quest,
    normalize_quest, original_quest, resume_quest, simulate_quest, verify_quest,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_original_quest_reaches_earned_alternate_ending():
    source = original_quest()
    saved = simulate_quest(source, demo_actions())
    assert saved["state"]["phase"] == "finished"
    assert saved["state"]["ending"] == "beacon_lit"
    assert saved["state"]["items"] == {"signal_beacon": 1}
    assert saved["state"]["crafted"] == ["beacon"]
    assert saved["state"]["choices"] == {"guide": "aid", "smith": "aid"}
    assert saved["state"]["expedition"]["state"]["phase"] == "won"
    assert saved["state"]["expedition"]["state"]["currency"] == 25
    assert verify_quest(json.loads(json.dumps(saved))) == saved
    assert import_quest(json.loads(json.dumps(export_quest(saved)))) == saved


def test_replay_resume_is_byte_stable_across_crafting_and_combat():
    actions = demo_actions()
    source = original_quest()
    whole = simulate_quest(source, actions)
    for split in (0, 1, 3, 5, 7, 10, len(actions)):
        partial = simulate_quest(source, actions[:split])
        continued = resume_quest(json.loads(json.dumps(partial)), actions[split:])
        assert continued == whole


def test_real_choice_consequences_select_distinct_victory_ending():
    actions = demo_actions()
    actions[0] = {"kind": "talk", "npc_id": "guide", "decision": "decline"}
    actions = [a for a in actions if a != {"kind": "craft", "recipe_id": "beacon"}]
    actions[-1] = {"kind": "finish", "ending_id": "quiet_victory"}
    saved = simulate_quest(original_quest(), actions)
    assert saved["state"]["ending"] == "quiet_victory"
    assert saved["state"]["items"] == {"ore": 1}
    assert saved["state"]["choices"]["guide"] == "decline"
    assert verify_quest(saved) == saved


@pytest.mark.parametrize("actions,pattern", [
    ([{"kind": "craft", "recipe_id": "beacon"}], "workshop"),
    ([{"kind": "travel", "to": "camp"},
      {"kind": "craft", "recipe_id": "beacon"}], "workshop"),
    ([{"kind": "travel", "to": "missing"}], "authored exit"),
    ([{"kind": "talk", "npc_id": "smith", "decision": "aid"}], "not present"),
    ([{"kind": "talk", "npc_id": "guide", "decision": "aid"},
      {"kind": "talk", "npc_id": "guide", "decision": "aid"}], "already recorded"),
    ([{"kind": "expedition", "action": {"kind": "fight"}}], "authored camp"),
    ([{"kind": "finish", "ending_id": "beacon_lit"}], "not earned"),
])
def test_no_teleport_free_crafting_or_unauthorized_rewards(actions, pattern):
    with pytest.raises(CombatSessionError, match=pattern):
        simulate_quest(original_quest(), actions)


def test_ending_cannot_be_forged_without_earned_items():
    actions = demo_actions()
    actions.remove({"kind": "craft", "recipe_id": "beacon"})
    with pytest.raises(CombatSessionError, match="required item"):
        simulate_quest(original_quest(), actions)


def test_no_action_after_terminal_and_no_double_reward():
    finished = simulate_quest(original_quest(), demo_actions())
    with pytest.raises(CombatSessionError, match="terminal"):
        _advance(finished, {"kind": "wait"})


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(world_id="other_world"),
    lambda x: x["locations"][0]["exits"].append("outside"),
    lambda x: x["locations"][1].update(id="dock"),
    lambda x: x["npcs"][0]["route"].append("outside"),
    lambda x: x["npcs"][1].update(id="guide"),
    lambda x: x["recipes"][0]["inputs"].append("unearned"),
    lambda x: x["recipes"][0].update(output="ore"),
    lambda x: x["endings"][0]["items"].append("unobtainable"),
    lambda x: x["endings"][0]["choices"].append(
        {"npc_id": "unknown", "decision": "aid"}),
    lambda x: x.update(schema_version="future"),
])
def test_bad_authored_source_rejected(mutate):
    source = original_quest()
    mutate(source)
    with pytest.raises(CombatSessionError):
        normalize_quest(source)


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"]["items"].update(signal_beacon=10),
    lambda x: x["state"]["choices"].update(guide="decline"),
    lambda x: x["state"]["expedition"]["state"].update(currency=99999),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["journal"][0]["action"].update(decision="decline"),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x["state"].update(ending="quiet_victory"),
])
def test_tampered_save_fails_replay(mutate):
    session = simulate_quest(original_quest(), demo_actions())
    bad = copy.deepcopy(session)
    mutate(bad)
    with pytest.raises(CombatSessionError):
        verify_quest(bad)


def test_bundle_tamper_and_source_binding():
    saved = simulate_quest(original_quest(), demo_actions())
    bundle = export_quest(saved)
    for mutate in (
        lambda x: x.update(checksum="0" * 64),
        lambda x: x.update(source_digest="0" * 64),
        lambda x: x["session"]["state"].update(location="forge"),
    ):
        bad = copy.deepcopy(bundle)
        mutate(bad)
        with pytest.raises(CombatSessionError):
            import_quest(bad)


def test_reject_oversized_and_noncanonical_input():
    source = original_quest()
    source["quest_id"] = "x" * 140000
    with pytest.raises(CombatSessionError, match="size budget"):
        normalize_quest(source)
    with pytest.raises(CombatSessionError):
        simulate_quest(original_quest(), [{"kind": "wait", "extra": True}])
    with pytest.raises(CombatSessionError):
        resume_quest(new_quest(original_quest()), [{"kind": "wait"}] * 97)


def test_cli_and_real_main_dispatch(capsys):
    from skeleton.__main__ import main
    assert main(["quest-expedition", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["ending"] == "beacon_lit"
    assert cli(["verify", "--session-json", json.dumps(saved)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"bad":true}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
