"""Replayable cooperative market timeline, safe branching and CLI acceptance."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_market_party import (
    export_party, import_party, original_party, simulate_party,
)
from skeleton.game.gameplay.scene_market_party_timeline import (
    cli, fork_party, inspect_party_timeline, seek_party,
    verify_party_fork, verify_party_timeline,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


@pytest.fixture
def campaign():
    source, turns = original_party()
    return source, turns, simulate_party(source, turns)


def test_seek_every_boundary_matches_canonical_replay(campaign):
    source, turns, completed = campaign
    for index in range(len(turns) + 1):
        expected = simulate_party(source, turns[:index])
        sought = seek_party(completed, index)
        assert sought == expected
        assert import_party(export_party(sought)) == sought


def test_paginated_timeline_is_deterministic_and_covers_every_event(campaign):
    _, turns, completed = campaign
    index = 0
    receipts = []
    while index < len(turns):
        report = inspect_party_timeline(completed, start=index, limit=3)
        assert verify_party_timeline(completed, json.loads(json.dumps(report))) == report
        assert report["next_sequence"] > index
        assert report["page_terminal_state_digest"] == seek_party(
            completed, report["next_sequence"])["state_digest"]
        receipts.extend(item["event_receipt"] for item in report["entries"])
        index = report["next_sequence"]
    assert receipts == [event["receipt"] for event in completed["journal"]]
    assert inspect_party_timeline(completed, start=len(turns))["entries"] == []


@pytest.mark.parametrize("sequence", [-1, True, 1.5, "0", 99999])
def test_seek_and_fork_reject_invalid_boundaries(campaign, sequence):
    _, _, completed = campaign
    with pytest.raises(SceneTravelError):
        seek_party(completed, sequence)
    with pytest.raises(SceneTravelError):
        fork_party(completed, sequence, [])


@pytest.mark.parametrize("limit", [0, -1, True, 33, 1.5])
def test_page_budget_rejected(campaign, limit):
    _, _, completed = campaign
    with pytest.raises(SceneTravelError):
        inspect_party_timeline(completed, limit=limit)


def test_fork_preserves_prefix_and_exact_earned_victory(campaign):
    _, turns, completed = campaign
    cut = len(turns) // 2
    original = copy.deepcopy(completed)
    result = fork_party(completed, cut, turns[cut:])
    assert result["fork_phase"] == "won"
    assert result["fork_state_digest"] == completed["state_digest"]
    assert result["prefix_state_digest"] == seek_party(
        completed, cut)["state_digest"]
    assert import_party(result["portable"]) == completed
    assert verify_party_fork(completed, json.loads(json.dumps(result))) == result
    assert completed == original


def test_alternative_pass_is_not_awarded_victory(campaign):
    _, turns, completed = campaign
    result = fork_party(completed, 0, [
        {"player_id": turns[0]["player_id"], "action": {"kind": "pass"}},
    ])
    assert result["fork_phase"] == "active"
    assert result["fork_state_digest"] != completed["state_digest"]
    assert verify_party_fork(completed, result) == result


def test_fork_rejects_illegal_actor_and_oversized_turns(campaign):
    _, turns, completed = campaign
    with pytest.raises(SceneTravelError):
        fork_party(completed, 0, [{"player_id": "intruder",
                                   "action": {"kind": "pass"}}])
    with pytest.raises(SceneTravelError):
        fork_party(completed, 0, [turns[0]] * 10000)


@pytest.mark.parametrize("field,value", [
    ("fork_save_digest", "0" * 64),
    ("parent_state_digest", "0" * 64),
    ("fork_phase", "active"),
    ("fork_state_digest", "0" * 64),
])
def test_tampered_fork_fails_even_if_checksum_recomputed(campaign, field, value):
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    _, turns, completed = campaign
    report = fork_party(completed, 0, turns)
    forged = copy.deepcopy(report)
    forged[field] = value
    assert forged != report  # prevent ineffective tamper cases
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_party_fork(completed, forged)


def test_invalid_fork_outer_checksum_is_rejected(campaign):
    _, turns, completed = campaign
    forged = fork_party(completed, 0, turns)
    assert forged["checksum"] != "0" * 64
    forged["checksum"] = "0" * 64
    with pytest.raises(SceneTravelError):
        verify_party_fork(completed, forged)


def test_tampered_page_and_stale_source_rejected(campaign):
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    source, turns, completed = campaign
    page = inspect_party_timeline(completed, limit=2)
    forged = copy.deepcopy(page)
    forged["entries"][0]["credits_delta"] = 999
    forged["checksum"] = dig({k: v for k, v in forged.items()
                              if k != "checksum"})
    with pytest.raises(SceneTravelError):
        verify_party_timeline(completed, forged)
    with pytest.raises(SceneTravelError):
        verify_party_timeline(simulate_party(source, turns[:-1]), page)


def test_cli_demo_and_main_dispatch(capsys):
    from skeleton.__main__ import main
    assert main(["scene-market-party-timeline", "demo"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["fork_phase"] == "won"
    assert cli(["page", "--session-json", "{}"]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
