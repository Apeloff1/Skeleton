"""Replay, author-policy, faction-consequence and CLI acceptance contracts."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.expedition_quest import demo_actions
from skeleton.game.gameplay.quest_factions import (
    _advance, cli, compare_factions, export_factions, import_factions,
    new_factions, normalize_factions, original_factions, resume_factions,
    simulate_factions, verify_factions,
)
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_playable_demo_earned_faction_ending_and_portable_save():
    saved = simulate_factions(original_factions(), demo_actions())
    assert saved["state"]["phase"] == "finished"
    assert saved["state"]["ending"] == "beacon_lit"
    assert saved["state"]["standing"] == {"harbor_wardens": 4}
    assert saved["state"]["quest"]["state"]["items"] == {"signal_beacon": 1}
    assert saved["state"]["quest"]["state"]["expedition"]["state"]["phase"] == "won"
    assert verify_factions(json.loads(json.dumps(saved))) == saved
    assert import_factions(json.loads(json.dumps(export_factions(saved)))) == saved


@pytest.mark.parametrize("split", [0, 1, 2, 4, 7, 10, 11])
def test_every_save_split_replays_identically(split):
    actions = demo_actions()
    whole = simulate_factions(original_factions(), actions)
    part = simulate_factions(original_factions(), actions[:split])
    assert resume_factions(part, actions[split:]) == whole


def test_decline_changes_standing_and_ending_branch():
    actions = demo_actions()
    actions[0] = {"kind": "talk", "npc_id": "guide", "decision": "decline"}
    actions = [a for a in actions if a != {"kind": "craft", "recipe_id": "beacon"}]
    actions[-1] = {"kind": "finish", "ending_id": "quiet_victory"}
    saved = simulate_factions(original_factions(), actions)
    assert saved["state"]["standing"] == {"harbor_wardens": 1}
    assert saved["state"]["ending"] == "quiet_victory"
    left = simulate_factions(original_factions(), demo_actions())
    report = compare_factions(left, saved)
    assert report["common_action_prefix"] == 0
    assert report["left"]["standing"] != report["right"]["standing"]


def test_unearned_faction_gate_rejects_even_when_base_quest_allows_ending():
    source = original_factions()
    source["ending_requirements"][0]["minimum_standing"][0]["minimum"] = 5
    with pytest.raises(CombatSessionError, match="standing ending not earned"):
        simulate_factions(source, demo_actions())


@pytest.mark.parametrize("mutation", [
    lambda x: x["factions"][0]["members"].append("missing"),
    lambda x: x["factions"][0]["members"].append("guide"),
    lambda x: x["factions"][0].update(aid_delta=True),
    lambda x: x["factions"][0].update(aid_delta=9),
    lambda x: x["ending_requirements"][0].update(ending_id="missing"),
    lambda x: x["ending_requirements"][0]["minimum_standing"][0].update(faction_id="missing"),
    lambda x: x["ending_requirements"].append(x["ending_requirements"][0]),
    lambda x: x.update(schema_version="future"),
])
def test_bad_source_fails_closed(mutation):
    source = original_factions()
    mutation(source)
    with pytest.raises(CombatSessionError):
        normalize_factions(source)


@pytest.mark.parametrize("mutation", [
    lambda x: x["state"]["standing"].update(harbor_wardens=999),
    lambda x: x["state"]["quest"]["state"].update(location="forge"),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["journal"][0]["action"].update(decision="decline"),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
    lambda x: x["state"].update(ending="quiet_victory"),
])
def test_tamper_is_rejected_by_nested_replay(mutation):
    saved = simulate_factions(original_factions(), demo_actions())
    bad = copy.deepcopy(saved)
    mutation(bad)
    with pytest.raises(CombatSessionError):
        verify_factions(bad)


def test_reject_forged_bundle_and_mismatched_sources():
    saved = simulate_factions(original_factions(), demo_actions())
    bundle = export_factions(saved)
    for mutate in (
        lambda x: x.update(checksum="0" * 64),
        lambda x: x.update(source_digest="0" * 64),
        lambda x: x["session"]["state"]["standing"].update(harbor_wardens=10),
    ):
        bad = copy.deepcopy(bundle)
        mutate(bad)
        with pytest.raises(CombatSessionError):
            import_factions(bad)
    changed = original_factions()
    changed["factions"][0]["aid_delta"] = 3
    with pytest.raises(CombatSessionError, match="different faction sources"):
        compare_factions(saved, new_factions(changed))


def test_rejected_action_does_not_mutate_saved_checkpoint():
    saved = new_factions(original_factions())
    frozen = copy.deepcopy(saved)
    with pytest.raises(CombatSessionError, match="authored exit"):
        _advance(saved, {"kind": "travel", "to": "outside"})
    assert saved == frozen
    with pytest.raises(CombatSessionError, match="invalid faction action batch"):
        resume_factions(saved, [{"kind": "wait"}] * 97)


def test_cli_is_reachable_from_real_main_and_roundtrips(capsys):
    from skeleton.__main__ import main
    assert main(["quest-factions", "demo"]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["state"]["standing"]["harbor_wardens"] == 4
    assert cli(["export", "--session-json", json.dumps(saved)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    assert cli(["simulate", "--source-json", '{"bad":true}',
                "--actions-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
