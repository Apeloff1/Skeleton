"""Campaign source -> canonical control rounds -> rewards -> replay -> export."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.arena_control import original_actions
from skeleton.game.gameplay.arena_control_campaign import (
    SCHEMA, advance_campaign, new_campaign, normalize_campaign,
    original_campaign, package_campaign, play_campaign, verify_campaign,
    verify_package,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError


def test_two_original_beacon_rounds_earn_only_verified_wins():
    source = original_campaign()
    played = play_campaign(source, [original_actions(), original_actions()])
    assert played["state"]["phase"] == "won"
    assert played["state"]["wins"] == 2
    assert played["state"]["currency"] == 30
    assert played["state"]["next_index"] == 2
    assert [stage["outcome"] for stage in played["state"]["rounds"]] == ["win", "win"]
    assert verify_campaign(json.loads(json.dumps(played))) == played
    assert all(event["control_session"]["state"]["winner"] == "wayfarers"
               for event in played["journal"])
    assert played["state_digest"] == dig(played["state"])


def test_resume_stage_matches_single_pass_and_source_remains_immutable():
    source = original_campaign()
    before = copy.deepcopy(source)
    initial = new_campaign(source)
    first = advance_campaign(initial, original_actions())
    first_before = copy.deepcopy(first)
    resumed = advance_campaign(first, original_actions())
    assert resumed == play_campaign(source, [original_actions(), original_actions()])
    assert first == first_before and source == before
    assert first["state"]["phase"] == "active"
    assert first["save"]["parent_save_digest"] == dig(initial["save"])
    assert resumed["save"]["parent_save_digest"] == dig(first["save"])
    with pytest.raises(CombatSessionError, match="terminal"):
        advance_campaign(resumed, original_actions())


@pytest.mark.parametrize("mutate", [
    lambda x: x["state"].update(currency=999),
    lambda x: x["state"]["rounds"][0].update(reward=999),
    lambda x: x["journal"][0].update(reward=999),
    lambda x: x["journal"][0]["control_session"]["state"]["scores"].update(wayfarers=999),
    lambda x: x["journal"][0]["actions"][0].update(direction="west"),
    lambda x: x["journal"][0].update(receipt="0" * 64),
    lambda x: x["save"].update(parent_save_digest=None),
    lambda x: x.update(source_digest="0" * 64),
])
def test_reward_and_journal_tampering_fail_closed(mutate):
    played = play_campaign(original_campaign(), [original_actions(), original_actions()])
    changed = copy.deepcopy(played)
    mutate(changed)
    with pytest.raises(CombatSessionError):
        verify_campaign(changed)


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(required_wins=3),
    lambda x: x.update(required_wins=True),
    lambda x: x["stages"][1]["control"].update(control_id="lantern_canal_control"),
    lambda x: x["stages"][1]["control"]["arena"].update(world_id="another_world"),
    lambda x: x["stages"][1].update(reward=-1),
    lambda x: x["stages"][1].update(reward=100001),
    lambda x: x.update(player_team="unknown"),
    lambda x: x["stages"].append(copy.deepcopy(x["stages"][0])),
    lambda x: x.update(schema_version="future"),
    lambda x: x.update(extra="untrusted"),
])
def test_invalid_campaign_source_rejected(mutate):
    source = original_campaign()
    mutate(source)
    with pytest.raises(CombatSessionError):
        normalize_campaign(source)


def test_nonterminal_round_cannot_release_rewards():
    source = original_campaign()
    with pytest.raises(CombatSessionError, match="must finish"):
        advance_campaign(new_campaign(source), original_actions()[:1])


def test_loss_and_draw_consequences_are_derived_not_author_claims():
    source = original_campaign()
    source["stages"][0]["control"]["score_target"] = 200
    source["stages"][0]["control"]["max_actions"] = 1
    source["stages"][1]["control"]["score_target"] = 200
    source["stages"][1]["control"]["max_actions"] = 1
    played = play_campaign(source, [original_actions()[:1], original_actions()[:1]])
    assert played["state"]["phase"] == "lost"
    assert played["state"]["wins"] == 0
    assert played["state"]["draws"] == 2
    assert played["state"]["currency"] == 0
    assert verify_campaign(played) == played


def test_portable_export_and_source_mismatch():
    source = original_campaign()
    first = advance_campaign(new_campaign(source), original_actions())
    package = package_campaign(first)
    assert package["manifest"]["currency"] == 10
    assert verify_package(json.loads(json.dumps(package))) == package
    bad = copy.deepcopy(package)
    bad["manifest"]["currency"] = 10000
    with pytest.raises(CombatSessionError):
        verify_package(bad)
    altered = copy.deepcopy(source)
    altered["stages"][0]["reward"] = 11
    with pytest.raises(CombatSessionError, match="source mismatch"):
        play_campaign(altered, [], resume=first)


def test_end_to_end_installed_cli_source_save_export_verify(capsys):
    assert main(["arena-control-campaign", "demo"]) == 0
    played = json.loads(capsys.readouterr().out)
    assert played["schema_version"] == SCHEMA
    assert played["state"]["currency"] == 30
    assert main([
        "arena-control-campaign", "verify", "--session-json", json.dumps(played),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == played
    assert main([
        "arena-control-campaign", "pack", "--session-json", json.dumps(played),
    ]) == 0
    portable = json.loads(capsys.readouterr().out)
    assert main([
        "arena-control-campaign", "unpack", "--package-json", json.dumps(portable),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == portable
