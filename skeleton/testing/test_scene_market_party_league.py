"""Real cooperative victory scoring, replay custody and league acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import original_party, simulate_party
from skeleton.game.gameplay.scene_market_party_league import (
    accept_league, cli, export_league, import_league, new_league,
    normalize_rules, rank_league, record_attempt, score_party, verify_league,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def victory():
    source, turns = original_party()
    return source, turns, simulate_party(source, turns)


def test_source_bound_earned_victory_and_portable_ranking(victory):
    source, turns, session = victory
    league = record_attempt(new_league(source), "first", session,
                            expected_revision=0)
    assert verify_league(json.loads(json.dumps(league))) == league
    assert import_league(json.loads(json.dumps(export_league(league)))) == league
    ranking = rank_league(league)
    assert ranking["ranking"][0]["rank"] == 1
    assert ranking["ranking"][0]["metrics"]["turns"] == len(turns)
    assert ranking["ranking"][0]["party_state_digest"] == session["state_digest"]
    assert ranking["checksum"] == dig({k: v for k, v in ranking.items()
                                       if k != "checksum"})


def test_no_unearned_victory_or_forged_currency(victory):
    source, turns, session = victory
    partial = simulate_party(source, turns[:1])
    with pytest.raises(SceneTravelError, match="earned victory"):
        record_attempt(new_league(source), "unfinished", partial,
                       expected_revision=0)
    forged = copy.deepcopy(session)
    forged["state"]["market"]["state"]["credits"] += 1000
    with pytest.raises(SceneTravelError):
        record_attempt(new_league(source), "counterfeit", forged,
                       expected_revision=0)


def test_stale_revision_duplicate_and_cross_source_fail_closed(victory):
    source, _, session = victory
    league = record_attempt(new_league(source), "a", session, expected_revision=0)
    snapshot = copy.deepcopy(league)
    with pytest.raises(SceneTravelError, match="stale"):
        record_attempt(league, "b", session, expected_revision=0)
    with pytest.raises(SceneTravelError, match="duplicate"):
        record_attempt(league, "a", session, expected_revision=1)
    wrong = copy.deepcopy(source)
    wrong["players"][0]["player_id"] = "other"
    with pytest.raises(SceneTravelError, match="source mismatch"):
        record_attempt(new_league(wrong), "wrong", session, expected_revision=0)
    assert league == snapshot


def test_deterministic_tie_order_and_no_source_mutation(victory):
    source, _, session = victory
    original = copy.deepcopy(session)
    league = new_league(source)
    for i, name in enumerate(("z", "a", "m")):
        league = record_attempt(league, name, session, expected_revision=i)
    assert [r["attempt_id"] for r in rank_league(league)["ranking"]] == ["a", "m", "z"]
    assert session == original


@pytest.mark.parametrize("field", ["state_digest", "entries", "journal", "rules"])
def test_recomputed_bundle_checksum_cannot_hide_tampering(victory, field):
    source, _, session = victory
    league = record_attempt(new_league(source), "a", session, expected_revision=0)
    forged = copy.deepcopy(league)
    if field == "state_digest":
        forged[field] = "0" * 64
    elif field == "entries":
        forged[field][0]["score"] += 100000
    elif field == "journal":
        forged[field][0]["receipt"] = "0" * 64
    else:
        forged[field]["victory"] += 1
    bundle = {"schema_version": "skeleton.scene_market_party_league_bundle.v1",
              "league": forged, "source_digest": forged["source_digest"],
              "state_digest": forged["state_digest"]}
    bundle["checksum"] = dig(bundle)
    with pytest.raises(SceneTravelError):
        import_league(bundle)


@pytest.mark.parametrize("rules", [
    {"victory": 0, "credits": 3, "goods": 5, "contributions": 7,
     "turns": -2, "passes": -3},
    {"victory": True, "credits": 3, "goods": 5, "contributions": 7,
     "turns": -2, "passes": -3},
    {"victory": 1000, "credits": -1, "goods": 5, "contributions": 7,
     "turns": -2, "passes": -3},
])
def test_invalid_scoring_contract_rejected(rules):
    with pytest.raises(SceneTravelError):
        normalize_rules(rules)


def test_end_to_end_cli_and_main_dispatch(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-league", "accept"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ranking"][0]["rank"] == 1
    assert cli(["rank", "--league-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
