"""Offline campaign integration: combat, rewards, save/replay and CLI."""
from __future__ import annotations
import copy
import json
import pytest
from skeleton.game.gameplay.combat_campaign import (
    CombatSessionError, advance_campaign, cli, finish_campaign,
    new_campaign, normalize_campaign, original_campaign, verify_campaign,
)
from skeleton.game.gameplay.turn_combat import verify_session


def test_original_patrol_rewards_only_verified_victories() -> None:
    campaign = original_campaign()
    result = finish_campaign(campaign)
    assert result["state"]["phase"] == "won"
    assert result["state"]["currency"] == 30
    assert result["state"]["next_index"] == 2
    assert len(result["state"]["encounters"]) == 2
    first, second = result["state"]["encounters"]
    assert first["reward"] == 10
    assert second["reward"] == 20
    assert second["combat"]["scenario"]["actors"][1]["max_hp"] <= 12
    assert verify_session(first["combat"]) == first["combat"]
    assert verify_campaign(json.loads(json.dumps(result))) == result


def test_durable_checkpoint_resume_matches_one_pass() -> None:
    source = original_campaign()
    initial = new_campaign(source)
    first = advance_campaign(initial)
    assert first["state"]["phase"] == "active"
    assert first["save"]["parent_save_digest"] is not None
    resumed = finish_campaign(source, resume=json.loads(json.dumps(first)))
    assert resumed == finish_campaign(source)
    assert first == advance_campaign(initial)


def test_tampered_reward_or_combat_hp_is_rejected() -> None:
    saved = advance_campaign(new_campaign(original_campaign()))
    bad = copy.deepcopy(saved)
    bad["state"]["currency"] += 100
    with pytest.raises(CombatSessionError, match="mismatch"):
        verify_campaign(bad)
    bad = copy.deepcopy(saved)
    bad["state"]["encounters"][0]["combat"]["state"]["actors"]["scout"]["hp"] = 999
    with pytest.raises(CombatSessionError, match="mismatch"):
        verify_campaign(bad)


@pytest.mark.parametrize("mutate", [
    lambda x: x["encounters"][0].update(reward=-1),
    lambda x: x["encounters"][0].update(reward=True),
    lambda x: x["encounters"][1]["scenario"].update(encounter_id="reed_watch"),
    lambda x: x["encounters"][1]["scenario"].update(world_id="elsewhere"),
    lambda x: x["encounters"][1]["scenario"]["actors"][0].update(attack=999),
    lambda x: x["encounters"][0]["scenario"].update(turn_limit=100),
    lambda x: x["encounters"].append(x["encounters"][0]),
    lambda x: x.update(extra="untrusted"),
])
def test_invalid_authored_campaign_fails_closed(mutate) -> None:
    source = original_campaign()
    mutate(source)
    with pytest.raises(CombatSessionError):
        normalize_campaign(source)


def test_source_mismatch_prevents_resume() -> None:
    source = original_campaign()
    saved = advance_campaign(new_campaign(source))
    changed = copy.deepcopy(source)
    changed["encounters"][1]["reward"] = 21
    with pytest.raises(CombatSessionError, match="source"):
        finish_campaign(changed, resume=saved)


def test_cli_demo_and_verify(capsys) -> None:
    assert cli(["demo"]) == 0
    session = json.loads(capsys.readouterr().out)
    assert session["state"]["currency"] == 30
    assert cli(["verify", "--session-json", json.dumps(session)]) == 0
    assert json.loads(capsys.readouterr().out) == session


def test_cli_invalid_input_exits_without_rewards(capsys) -> None:
    assert cli(["simulate", "--source-json", '{"bad":true}']) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["ok"] is False
