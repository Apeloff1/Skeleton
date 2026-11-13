"""Source-bound playable handoff, lease, integrity and portable acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import original_party, simulate_party
from skeleton.game.gameplay.scene_market_party_handoff import (
    accept_handoff, apply_handoff, cli, plan_handoff, verify_handoff,
)
from skeleton.game.gameplay.scene_market_party_league import new_league
from skeleton.game.gameplay.scene_market_party_vault import (
    new_vault, read_slot, transact_vault,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def campaign():
    source, turns = original_party()
    played = simulate_party(source, turns)
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": played,
    })
    return source, turns, played, vault, new_league(source)


def plan(campaign, **overrides):
    _, turns, _, vault, league = campaign
    args = dict(from_slot="campaign", to_slot="branch",
                sequence=len(turns) // 2, turns=turns[len(turns) // 2:],
                attempt_id="branch-win", expected_vault_revision=1,
                expected_league_revision=0)
    args.update(overrides)
    return plan_handoff(vault, league, **args)


def test_replay_fork_cas_rank_and_portable_roundtrip(campaign):
    _, _, played, vault, league = campaign
    before_vault, before_league = copy.deepcopy(vault), copy.deepcopy(league)
    receipt = plan(campaign)
    assert verify_handoff(vault, league, json.loads(json.dumps(receipt))) == receipt
    result = apply_handoff(vault, league, receipt)
    assert result["checkpoint"] == played
    assert read_slot(result["vault"], "branch") == played
    assert read_slot(result["vault"], "campaign") == played
    assert result["vault"]["revision"] == 2
    assert result["league"]["revision"] == 1
    assert result["portfolio"]["slot"] == "branch"
    assert result["portfolio"]["ranking"]["ranking"][0]["attempt_id"] == "branch-win"
    assert vault == before_vault and league == before_league
    assert result["receipt_checksum"] == receipt["checksum"]


@pytest.mark.parametrize("changes", [
    {"from_slot": "missing"}, {"to_slot": "campaign"},
    {"sequence": -1}, {"sequence": True},
    {"attempt_id": "x" * 49}, {"expected_vault_revision": 0},
    {"expected_league_revision": 1}, {"turns": {}},
])
def test_invalid_or_stale_handoff_fails_closed(campaign, changes):
    with pytest.raises((SceneTravelError, TypeError, ValueError)):
        plan(campaign, **changes)


def test_duplicate_slot_and_duplicate_attempt_rejected(campaign):
    _, _, _, vault, league = campaign
    receipt = plan(campaign)
    applied = apply_handoff(vault, league, receipt)
    with pytest.raises(SceneTravelError):
        plan_handoff(applied["vault"], applied["league"],
                     from_slot="campaign", to_slot="branch",
                     sequence=0, turns=[], attempt_id="second",
                     expected_vault_revision=2, expected_league_revision=1)
    with pytest.raises(SceneTravelError):
        plan_handoff(applied["vault"], applied["league"],
                     from_slot="campaign", to_slot="other",
                     sequence=0, turns=[], attempt_id="branch-win",
                     expected_vault_revision=2, expected_league_revision=1)


@pytest.mark.parametrize("field", [
    "child_state_digest", "portfolio", "fork_proof", "vault_bundle",
    "league_bundle", "sequence", "qualification",
])
def test_recomputed_checksum_does_not_authorize_forged_handoff(campaign, field):
    _, _, _, vault, league = campaign
    forged = copy.deepcopy(plan(campaign))
    if field == "sequence":
        forged[field] = 0
    elif field == "portfolio":
        forged[field]["ranking"]["ranking"][0]["score"] += 999
    elif field == "fork_proof":
        forged[field]["fork_state_digest"] = "0" * 64
    elif field == "vault_bundle":
        forged[field]["vault"]["revision"] += 1
    elif field == "league_bundle":
        forged[field]["league"]["revision"] += 1
    elif field == "qualification":
        forged[field] = "signed_device_release"
    else:
        forged[field] = "0" * 64
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_handoff(vault, league, forged)


def test_stale_parent_after_lease_movement_rejected(campaign):
    _, _, played, vault, league = campaign
    receipt = plan(campaign)
    moved = transact_vault(vault, {
        "kind": "put", "slot": "other", "expected_revision": 1,
        "expected_slot_digest": None, "checkpoint": played,
    })
    with pytest.raises(SceneTravelError, match="stale"):
        apply_handoff(moved, league, receipt)


def test_cross_source_league_and_unearned_fork_rejected(campaign):
    source, turns, _, vault, _ = campaign
    wrong = copy.deepcopy(source)
    wrong["players"][0]["player_id"] = "foreign"
    with pytest.raises(SceneTravelError, match="source mismatch"):
        plan_handoff(vault, new_league(wrong),
                     from_slot="campaign", to_slot="branch",
                     sequence=0, turns=turns, attempt_id="branch-win",
                     expected_vault_revision=1, expected_league_revision=0)
    with pytest.raises(SceneTravelError, match="earned victory"):
        plan(campaign, turns=[])


def test_cli_main_dispatch_and_error_channel(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-handoff", "accept"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["phase"] == "won"
    assert result["qualification"].endswith("not_device_release")
    assert cli(["verify", "--vault-json", "{}", "--league-json", "{}",
                "--receipt-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_repeated_acceptance_is_deterministic():
    assert accept_handoff() == accept_handoff()
