"""Real player turn -> canonical enemies -> durable combat campaign replay."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.combat_campaign import original_campaign
from skeleton.game.gameplay.combat_campaign_interactive import (
    advance_interactive, demo_interactive, new_interactive,
    package_interactive, resume_interactive, verify_interactive,
    verify_interactive_package,
)
from skeleton.game.gameplay.tactical_policy import choose_action
from skeleton.game.gameplay.turn_combat import CombatSessionError, verify_session


def _hero_choice(snapshot):
    action = choose_action(snapshot["state"]["current_combat"])
    return {key: value for key, value in action.items() if key != "actor_id"}


def test_original_campaign_player_reaches_canonical_victory_and_rewards():
    finished = demo_interactive()
    assert finished["state"]["phase"] == "won"
    assert finished["state"]["currency"] == 30
    assert finished["state"]["encounter_index"] == 2
    assert len(finished["state"]["encounters"]) == 2
    assert len(finished["state"]["choices"]) > 0
    for encounter in finished["state"]["encounters"]:
        assert verify_session(encounter["combat"]) == encounter["combat"]
    assert verify_interactive(json.loads(json.dumps(finished))) == finished


def test_checkpoint_and_resume_replay_match_single_pass():
    initial = new_interactive(original_campaign())
    assert initial["state"]["phase"] == "active"
    choice = _hero_choice(initial)
    first = advance_interactive(initial, choice)
    assert first["save"]["parent_save_digest"] is not None
    assert first["state"]["choices"] == [choice]
    assert resume_interactive(initial, [choice]) == first
    assert verify_interactive(first) == first
    assert initial == new_interactive(original_campaign())


def test_player_cannot_control_opponents_or_attack_own_team():
    initial = new_interactive(original_campaign())
    with pytest.raises(CombatSessionError):
        advance_interactive(initial, {
            "kind": "attack", "actor_id": "warden", "target_id": "scout",
        })
    with pytest.raises(CombatSessionError):
        advance_interactive(initial, {"kind": "attack", "target_id": "scout"})
    with pytest.raises(CombatSessionError):
        advance_interactive(initial, {"kind": "attack", "target_id": "unknown"})


@pytest.mark.parametrize("choice", [
    {"kind": "cast", "spell": "win"},
    {"kind": "guard", "target_id": "warden"},
    {"kind": "rest", "actor_id": "warden"},
    {"kind": "attack"},
    {"kind": "attack", "target_id": 123},
    {"kind": "guard", "extra": True},
    {},
])
def test_invalid_hero_actions_fail_closed(choice):
    initial = new_interactive(original_campaign())
    with pytest.raises(CombatSessionError):
        advance_interactive(initial, choice)


@pytest.mark.parametrize("edit", [
    lambda x: x["state"].update(currency=999),
    lambda x: x["state"].update(hero_hp=999),
    lambda x: x["state"]["choices"].append({"kind": "rest"}),
    lambda x: x["state"]["current_combat"]["state"].update(phase="won"),
    lambda x: x["save"].update(parent_save_digest="fake"),
    lambda x: x.update(source_digest="fake"),
])
def test_tampered_choice_journal_state_or_save_fails_closed(edit):
    initial = new_interactive(original_campaign())
    first = advance_interactive(initial, _hero_choice(initial))
    forged = copy.deepcopy(first)
    edit(forged)
    with pytest.raises(CombatSessionError):
        verify_interactive(forged)


def test_portable_checkpoint_and_terminal_package_round_trip():
    initial = new_interactive(original_campaign())
    checkpoint = package_interactive(initial)
    assert verify_interactive_package(json.loads(json.dumps(checkpoint))) == checkpoint
    completed = demo_interactive()
    portable = package_interactive(completed)
    assert portable["manifest"]["currency"] == 30
    assert verify_interactive_package(json.loads(json.dumps(portable))) == portable
    with pytest.raises(CombatSessionError, match="terminal"):
        advance_interactive(completed, {"kind": "rest"})


def _run(capsys, *args):
    status = main(list(args))
    result = capsys.readouterr()
    return status, json.loads(result.out or result.err)


def test_main_cli_play_save_resume_verify_package(capsys):
    source = original_campaign()
    status, initial = _run(capsys, "combat-campaign-play", "start",
                           "--source-json", json.dumps(source))
    assert status == 0 and initial["state"]["phase"] == "active"
    choice = _hero_choice(initial)
    status, next_save = _run(capsys, "combat-campaign-play", "act",
                             "--session-json", json.dumps(initial),
                             "--command-json", json.dumps(choice))
    assert status == 0 and next_save["state"]["choices"] == [choice]
    status, checked = _run(capsys, "combat-campaign-play", "verify",
                           "--session-json", json.dumps(next_save))
    assert status == 0 and checked == next_save
    status, portable = _run(capsys, "combat-campaign-play", "pack",
                            "--session-json", json.dumps(next_save))
    assert status == 0
    status, unpacked = _run(capsys, "combat-campaign-play", "unpack",
                            "--package-json", json.dumps(portable))
    assert status == 0 and unpacked == portable


def test_cli_bad_source_fails_without_player_reward(capsys):
    status, error = _run(capsys, "combat-campaign-play", "start",
                         "--source-json", '{"bad":true}')
    assert status == 2 and error["ok"] is False
