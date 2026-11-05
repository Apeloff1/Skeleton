"""Reachable mission softlocks are canonical, replayable, and never hidden."""
from __future__ import annotations

import copy
import json

import pytest

from skeleton.game.gameplay.scene_mission import (
    demo_actions, original_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_liveness import (
    audit_liveness, cli, verify_liveness,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def locked_source():
    source = original_mission()
    for ending in source["endings"]:
        ending["min_reputation"] = 9999
    return source


def stuck_checkpoint():
    return simulate_mission(locked_source(), demo_actions()[:-1])


def test_unfinishable_authored_mission_is_detected_from_playable_checkpoint():
    checkpoint = stuck_checkpoint()
    report = audit_liveness(session=checkpoint, max_states=8, max_depth=4)
    assert report["status"] == "softlock_found"
    assert report["complete"] is True
    assert report["states_explored"] == 1
    assert report["softlocks"][0]["actions"] == []
    assert report["softlocks"][0]["scene_phase"] != "active"
    assert report["softlocks"][0]["safe_fallback"].startswith("restore")
    assert verify_liveness(json.loads(json.dumps(report)), session=checkpoint) == report


def test_small_budget_does_not_certify_a_clean_game():
    report = audit_liveness(original_mission(), max_states=1, max_depth=1)
    assert report["status"] == "inconclusive"
    assert report["complete"] is False
    assert report["budget_exhausted"] is True
    assert verify_liveness(report, source=original_mission()) == report


def test_terminal_checkpoint_has_no_active_softlock():
    finished = simulate_mission(original_mission(), demo_actions())
    report = audit_liveness(session=finished, max_states=4, max_depth=2)
    assert report["status"] == "no_softlock"
    assert report["complete"] is True
    assert report["softlocks"] == []
    assert report["reachable_endings"][0]["ending_id"] == finished["state"]["ending"]
    assert verify_liveness(report, session=finished) == report


@pytest.mark.parametrize("field,value", [
    ("source_digest", "0" * 64),
    ("initial_state_digest", "0" * 64),
    ("status", "no_softlock"),
    ("complete", False),
    ("states_explored", 9),
    ("checksum", "0" * 64),
    ("max_depth", 0),
    ("softlocks", []),
])
def test_tampered_liveness_receipt_rejected(field, value):
    checkpoint = stuck_checkpoint()
    report = audit_liveness(session=checkpoint, max_states=8, max_depth=4)
    bad = copy.deepcopy(report)
    bad[field] = value
    if bad == report:
        pytest.skip("mutation equals original receipt")
    with pytest.raises(SceneTravelError):
        verify_liveness(bad, session=checkpoint)


def test_recomputed_checksum_cannot_fake_an_earned_exit():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    checkpoint = stuck_checkpoint()
    report = audit_liveness(session=checkpoint, max_states=8, max_depth=4)
    report["softlocks"][0]["reputation"] = 10000
    report["checksum"] = dig({k: v for k, v in report.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="replay"):
        verify_liveness(report, session=checkpoint)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": True}, {"max_states": 4097},
    {"max_depth": 0}, {"max_depth": 129},
    {"max_findings": 0}, {"max_findings": 17},
])
def test_invalid_budgets_fail_closed(kwargs):
    with pytest.raises(SceneTravelError):
        audit_liveness(session=stuck_checkpoint(), **kwargs)


def test_installed_cli_detects_softlock_and_verifies_receipt(capsys):
    from skeleton.__main__ import main
    checkpoint = stuck_checkpoint()
    assert main(["scene-mission-liveness", "--session-json",
                 json.dumps(checkpoint), "--max-states", "8"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "softlock_found"
    assert cli(["--session-json", json.dumps(checkpoint),
                "--verify-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_cli_invalid_source_returns_nonzero(capsys):
    assert cli(["--source-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
