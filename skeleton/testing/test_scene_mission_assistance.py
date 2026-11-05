"""Player hints are source-bound, observational and replay-proven."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_mission import (
    demo_actions, original_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_assistance import (
    assist_mission, cli, verify_assistance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def near_terminal():
    return simulate_mission(original_mission(), demo_actions()[:-1])


def test_hint_from_checkpoint_previews_only_legal_earned_ending():
    checkpoint = near_terminal()
    before = copy.deepcopy(checkpoint)
    hint = assist_mission(session=checkpoint, target_ending="lantern_restored",
                          max_states=16, max_depth=2)
    assert hint["status"] == "found"
    assert hint["suggested_action"] == {
        "kind": "finish", "ending_id": "lantern_restored",
    }
    assert hint["preview"]["ending"] == "lantern_restored"
    assert hint["preview"]["portable_checksum"]
    assert hint["mutated_session"] is False
    assert checkpoint == before
    assert verify_assistance(json.loads(json.dumps(hint)), session=checkpoint) == hint


def test_already_earned_ending_does_not_suggest_an_illegal_second_finish():
    checkpoint = simulate_mission(original_mission(), demo_actions())
    hint = assist_mission(session=checkpoint, target_ending="lantern_restored",
                          max_states=4, max_depth=2)
    assert hint["status"] == "found"
    assert hint["suggested_action"] is None
    assert hint["route_actions"] == []
    assert hint["preview"] is None


def test_search_budget_exhaustion_returns_no_unverified_advice():
    hint = assist_mission(original_mission(), target_ending="lantern_restored",
                          max_states=1, max_depth=1)
    assert hint["status"] == "inconclusive"
    assert hint["suggested_action"] is None
    assert hint["preview"] is None
    assert hint["budget_exhausted"] is True


@pytest.mark.parametrize("field,value", [
    ("source_digest", "0" * 64),
    ("suggested_action", {"kind": "finish", "ending_id": "sinkhole_failure"}),
    ("mutated_session", True),
    ("receipt", "0" * 64),
    ("max_states", 0),
    ("route_actions", []),
    ("explanation", "Free reward"),
])
def test_tampered_hint_is_rejected(field, value):
    checkpoint = near_terminal()
    hint = assist_mission(session=checkpoint, target_ending="lantern_restored",
                          max_states=16, max_depth=2)
    forged = copy.deepcopy(hint)
    forged[field] = value
    if forged == hint:
        pytest.skip("mutation equals real receipt")
    with pytest.raises(SceneTravelError):
        verify_assistance(forged, session=checkpoint)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": True}, {"max_states": 4097},
    {"max_depth": 0}, {"max_depth": True}, {"max_depth": 129},
    {"target_ending": "nonexistent"},
])
def test_bad_budgets_and_unearned_endings_rejected(kwargs):
    with pytest.raises(SceneTravelError):
        assist_mission(session=near_terminal(), target_ending=kwargs.get(
            "target_ending", "lantern_restored",
        ), **{k: v for k, v in kwargs.items() if k != "target_ending"})


def test_installed_cli_exposes_replay_verified_hint(capsys):
    from skeleton.__main__ import main
    checkpoint = near_terminal()
    assert main(["scene-mission-assist", "--session-json", json.dumps(checkpoint),
                 "--ending-id", "lantern_restored", "--max-states", "16",
                 "--max-depth", "2"]) == 0
    hint = json.loads(capsys.readouterr().out)
    assert hint["suggested_action"]["kind"] == "finish"
    assert cli(["--session-json", json.dumps(checkpoint),
                "--verify-json", json.dumps(hint)]) == 0
    assert json.loads(capsys.readouterr().out) == hint


def test_cli_invalid_source_fails_closed(capsys):
    assert cli(["--source-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
