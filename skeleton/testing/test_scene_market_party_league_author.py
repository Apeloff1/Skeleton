"""Transactional league rule authoring, real preview and forged-edit rejection."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market_party import original_party, simulate_party
from skeleton.game.gameplay.scene_market_party_league import (
    new_league, record_attempt,
)
from skeleton.game.gameplay.scene_market_party_league_author import (
    cli, edit_league, preview_league, verify_league_edit,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def authored():
    source, turns = original_party()
    league = new_league(source)
    session = simulate_party(source, turns)
    return league, session


def test_edit_receipt_and_playable_preview_roundtrip(authored):
    league, session = authored
    before = copy.deepcopy(league)
    receipt = edit_league(league, {"credits": 4, "passes": -4},
                          expected_state_digest=league["state_digest"])
    assert verify_league_edit(league, json.loads(json.dumps(receipt))) == receipt
    assert receipt["league"]["rules"]["credits"] == 4
    assert receipt["league"]["source_digest"] == league["source_digest"]
    report = preview_league(receipt["league"], session)
    assert report["ranking"]["ranking"][0]["party_state_digest"] == session["state_digest"]
    assert report["checksum"] == dig({k: v for k, v in report.items()
                                     if k != "checksum"})
    assert league == before


def test_stale_lease_noop_and_illegal_rule_fail_closed(authored):
    league, _ = authored
    with pytest.raises(SceneTravelError, match="stale"):
        edit_league(league, {"credits": 4}, expected_state_digest="0" * 64)
    with pytest.raises(SceneTravelError, match="no effect"):
        edit_league(league, {"credits": 3},
                    expected_state_digest=league["state_digest"])
    with pytest.raises(SceneTravelError):
        edit_league(league, {"credits": -4},
                    expected_state_digest=league["state_digest"])
    with pytest.raises(SceneTravelError):
        edit_league(league, {"untrusted": 1},
                    expected_state_digest=league["state_digest"])


def test_post_attempt_edit_rejected(authored):
    league, session = authored
    scored = record_attempt(league, "won", session, expected_revision=0)
    with pytest.raises(SceneTravelError, match="after scored"):
        edit_league(scored, {"credits": 4},
                    expected_state_digest=scored["state_digest"])


def test_forged_receipt_rejected_even_with_recomputed_checksum(authored):
    league, _ = authored
    receipt = edit_league(league, {"credits": 4},
                          expected_state_digest=league["state_digest"])
    forged = copy.deepcopy(receipt)
    forged["league"]["rules"]["credits"] = 999
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_league_edit(league, forged)


def test_preview_rejects_incomplete_and_foreign_source(authored):
    league, _ = authored
    source, turns = original_party()
    with pytest.raises(SceneTravelError):
        preview_league(league, simulate_party(source, turns[:1]))
    foreign = copy.deepcopy(source)
    foreign["players"][0]["player_id"] = "another"
    with pytest.raises(SceneTravelError):
        preview_league(new_league(foreign), simulate_party(source, turns))


def test_cli_main_dispatch(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-league-author", "demo"]) == 0
    assert json.loads(capsys.readouterr().out)["ranking"]["revision"] == 1
    assert cli(["edit", "--league-json", "{}", "--patch-json", "{}",
                "--expected-state-digest", "x"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
