"""Offline mission league source, replay, CAS and packaging acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_mission import (
    demo_actions, original_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_league import (
    cli, demo_league, export_league, import_league, inspect_league,
    new_league, normalize_rules, original_rules, submit_league, verify_league,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def _finished():
    return simulate_mission(original_mission(), demo_actions())


def test_demo_league_is_replay_verified_and_ranked():
    league = demo_league()
    assert league["revision"] == 2
    assert verify_league(json.loads(json.dumps(league))) == league
    ranking = inspect_league(league)["ranking"]
    assert [e["attempt_id"] for e in ranking] == ["restored", "unpledged"]
    assert ranking[0]["score"] > ranking[1]["score"]
    assert ranking[0]["ending"] == "lantern_restored"
    assert import_league(json.loads(json.dumps(export_league(league)))) == league


def test_scores_are_earned_from_runtime_not_untrusted_submissions():
    league = new_league(original_mission(), original_rules())
    finished = _finished()
    updated = submit_league(
        league, "one", finished, expected_digest=league["league_digest"],
    )
    assert updated["entries"][0]["score"] == (
        3 * 50 + 6 * 4 + 200 - 5 * 3
    )
    assert updated["entries"][0]["session"] == finished
    assert updated["entries"][0]["state_digest"] == finished["state_digest"]


def test_optimistic_cas_rejects_stale_writer_and_duplicate_attempt():
    league = new_league(original_mission(), original_rules())
    original_digest = league["league_digest"]
    updated = submit_league(league, "one", _finished(),
                            expected_digest=original_digest)
    with pytest.raises(SceneTravelError, match="stale"):
        submit_league(updated, "two", _finished(), expected_digest=original_digest)
    with pytest.raises(SceneTravelError, match="duplicate league attempt"):
        submit_league(updated, "one", _finished(),
                      expected_digest=updated["league_digest"])
    with pytest.raises(SceneTravelError, match="duplicate league replay"):
        submit_league(updated, "two", _finished(),
                      expected_digest=updated["league_digest"])


@pytest.mark.parametrize("change", [
    lambda league: league["entries"][0].update(score=999999),
    lambda league: league["entries"][0].update(ending="unearned"),
    lambda league: league["entries"][0]["session"]["state"].update(reputation=999),
    lambda league: league["entries"][0]["session"]["journal"][0].update(receipt="0"*64),
    lambda league: league.update(league_digest="0"*64),
    lambda league: league["rules"].update(victory_bonus=5000),
    lambda league: league.update(revision=True),
    lambda league: league["entries"][0].update(fake_grant=100),
])
def test_replay_score_or_metadata_tampering_fails_closed(change):
    forged = copy.deepcopy(demo_league())
    change(forged)
    with pytest.raises(SceneTravelError):
        verify_league(forged)


def test_unfinished_and_foreign_source_cannot_enter_league():
    league = new_league(original_mission(), original_rules())
    unfinished = simulate_mission(original_mission(), [])
    with pytest.raises(SceneTravelError, match="must finish"):
        submit_league(league, "unfinished", unfinished,
                      expected_digest=league["league_digest"])
    foreign = original_mission()
    foreign["director_id"] = "other_director"
    session = simulate_mission(foreign, demo_actions())
    with pytest.raises(SceneTravelError, match="source mismatch"):
        submit_league(league, "foreign", session,
                      expected_digest=league["league_digest"])


@pytest.mark.parametrize("field,value", [
    ("action_cost", -1),
    ("action_cost", True),
    ("mission_points", 1001),
    ("reputation_multiplier", 11),
    ("victory_bonus", 5001),
    ("defeat_penalty", -1),
    ("rules_id", "../unsafe"),
])
def test_bad_rules_are_rejected(field, value):
    rules = original_rules()
    rules[field] = value
    with pytest.raises(SceneTravelError):
        normalize_rules(rules)


def test_entry_count_is_bounded_even_for_syntactically_valid_json():
    league = demo_league()
    bad = copy.deepcopy(league)
    bad["entries"] = bad["entries"] * 5
    bad["revision"] = 10
    with pytest.raises(SceneTravelError, match="entries"):
        verify_league(bad)


def test_bundle_integrity_does_not_trust_supplied_digest():
    bundle = export_league(demo_league())
    for change in (
        lambda b: b.update(checksum="0"*64),
        lambda b: b.update(source_digest="0"*64),
        lambda b: b["league"]["entries"][0].update(score=10**8),
    ):
        bad = copy.deepcopy(bundle)
        change(bad)
        with pytest.raises(SceneTravelError):
            import_league(bad)


def test_installed_cli_supports_demo_inspect_export_import_and_errors(capsys):
    from skeleton.__main__ import main
    assert main(["scene-mission-league", "demo"]) == 0
    league = json.loads(capsys.readouterr().out)
    assert league["revision"] == 2
    assert cli(["inspect", "--league-json", json.dumps(league)]) == 0
    assert json.loads(capsys.readouterr().out)["ranking"][0]["rank"] == 1
    assert cli(["export", "--league-json", json.dumps(league)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli(["import", "--bundle-json", json.dumps(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == league
    assert cli(["verify", "--league-json", json.dumps(league)]) == 0
    assert json.loads(capsys.readouterr().out) == league
    assert cli(["new", "--source-json", json.dumps(original_mission()),
                "--rules-json", json.dumps(original_rules())]) == 0
    empty = json.loads(capsys.readouterr().out)
    assert cli(["submit", "--league-json", json.dumps(empty),
                "--session-json", json.dumps(_finished()),
                "--attempt-id", "first",
                "--expected-digest", empty["league_digest"]]) == 0
    assert json.loads(capsys.readouterr().out)["revision"] == 1
    assert cli(["inspect", "--league-json", '{"x":1,"x":2}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
