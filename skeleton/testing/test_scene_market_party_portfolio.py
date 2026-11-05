"""Portable source→play→save→league→export cooperative acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import original_party, simulate_party
from skeleton.game.gameplay.scene_market_party_league import (
    new_league, record_attempt,
)
from skeleton.game.gameplay.scene_market_party_portfolio import (
    accept_portfolio, cli, import_portfolio, pack_portfolio,
)
from skeleton.game.gameplay.scene_market_party_vault import (
    new_vault, transact_vault,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def complete():
    source, turns = original_party()
    played = simulate_party(source, turns)
    vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": played})
    league = record_attempt(new_league(source), "victory", played,
                            expected_revision=0)
    return source, played, vault, league


def test_full_portfolio_roundtrip_and_earned_rank(complete):
    _, played, vault, league = complete
    original = copy.deepcopy(played)
    bundle = pack_portfolio(played, vault, league, slot="campaign")
    assert import_portfolio(json.loads(json.dumps(bundle))) == bundle
    assert bundle["ranking"]["ranking"][0]["party_state_digest"] == played["state_digest"]
    assert bundle["checksum"] == dig({k: v for k, v in bundle.items()
                                     if k != "checksum"})
    assert played == original


def test_missing_slot_and_source_mismatch_rejected(complete):
    source, played, vault, league = complete
    with pytest.raises(SceneTravelError):
        pack_portfolio(played, vault, league, slot="unknown")
    wrong = copy.deepcopy(source)
    wrong["players"][0]["player_id"] = "foreign"
    with pytest.raises(SceneTravelError, match="source mismatch"):
        pack_portfolio(played, vault, new_league(wrong), slot="campaign")


def test_incomplete_saved_game_rejected_against_ranked_victory(complete):
    source, _, vault, league = complete
    partial = simulate_party(source, [])
    with pytest.raises(SceneTravelError, match="selected save mismatch"):
        pack_portfolio(partial, vault, league, slot="campaign")


@pytest.mark.parametrize("field", ["party_state_digest", "ranking", "slot", "party"])
def test_forged_portfolio_rejected_even_with_recomputed_checksum(complete, field):
    _, played, vault, league = complete
    bundle = pack_portfolio(played, vault, league, slot="campaign")
    forged = copy.deepcopy(bundle)
    if field == "party_state_digest":
        forged[field] = "0" * 64
    elif field == "ranking":
        forged[field]["ranking"][0]["score"] += 100000
    elif field == "slot":
        forged[field] = "other"
    else:
        forged[field]["session"]["state"]["market"]["state"]["credits"] += 999
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        import_portfolio(forged)


def test_end_to_end_main_dispatch_and_error_channel(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-portfolio", "accept"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["phase"] == "won"
    assert result["ranking"]["revision"] == 1
    assert cli(["import", "--bundle-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)


def test_portfolio_refuses_unranked_victory(complete):
    source, played, vault, _ = complete
    with pytest.raises(SceneTravelError, match="earned ranked victory"):
        pack_portfolio(played, vault, new_league(source), slot="campaign")


def test_portfolio_refuses_unearned_checkpoint_even_with_valid_rank(complete):
    source, _, _, league = complete
    partial = simulate_party(source, [])
    partial_vault = transact_vault(new_vault(source), {
        "kind": "put", "slot": "campaign", "expected_revision": 0,
        "expected_slot_digest": None, "checkpoint": partial})
    with pytest.raises(SceneTravelError, match="winning checkpoint"):
        pack_portfolio(partial, partial_vault, league, slot="campaign")
