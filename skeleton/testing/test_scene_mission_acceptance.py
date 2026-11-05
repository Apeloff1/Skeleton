"""Mission ending acceptance must prove real runtime and portable replay."""
from __future__ import annotations

import copy
import json
import pytest

from skeleton.game.gameplay.scene_mission import (
    demo_actions, original_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_acceptance import (
    accept_mission, cli, verify_acceptance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_original_restored_ending_is_replay_export_and_consequence_verified():
    source = original_mission()
    report = accept_mission(source, ending_id="lantern_restored",
                            max_states=512, max_depth=32)
    assert report["accepted"] is True
    assert len(report["findings"]) == 1
    item = report["findings"][0]
    assert item["status"] == "found"
    assert item["terminal"]["reputation"] >= 5
    assert "reach_sanctuary" in item["terminal"]["missions"]
    assert item["terminal"]["bundle_checksum"]
    assert verify_acceptance(json.loads(json.dumps(report)), source=source) == report


def test_budget_exhaustion_never_certifies_a_nonexistent_witness():
    report = accept_mission(original_mission(), ending_id="lantern_restored",
                            max_states=1, max_depth=1)
    assert report["accepted"] is False
    assert report["findings"][0]["status"] == "inconclusive"
    assert report["findings"][0]["budget_exhausted"] is True
    assert report["findings"][0]["terminal"] is None


def test_terminal_checkpoint_only_certifies_earned_ending():
    saved = simulate_mission(original_mission(), demo_actions())
    report = accept_mission(session=saved, max_states=8, max_depth=4)
    findings = {x["ending_id"]: x for x in report["findings"]}
    assert findings["lantern_restored"]["status"] == "found"
    assert findings["lantern_restored"]["actions"] == []
    assert findings["sinkhole_failure"]["status"] == "unreachable"
    assert report["accepted"] is False


@pytest.mark.parametrize("field,value", [
    ("source_digest", "0" * 64),
    ("accepted", False),
    ("checksum", "0" * 64),
    ("max_states", 1),
    ("target_ending", "unpledged_victory"),
])
def test_forged_acceptance_receipt_rejected(field, value):
    source = original_mission()
    report = accept_mission(source, ending_id="lantern_restored",
                            max_states=512, max_depth=32)
    bad = copy.deepcopy(report)
    bad[field] = value
    if bad == report:
        pytest.skip("mutation coincides with real receipt")
    with pytest.raises(SceneTravelError):
        verify_acceptance(bad, source=source)


def test_forged_terminal_evidence_rejected_even_with_checksum_recomputed():
    from skeleton.game.gameplay.flgb_gameplay_runtime import dig
    source = original_mission()
    bad = accept_mission(source, ending_id="lantern_restored",
                         max_states=512, max_depth=32)
    bad["findings"][0]["terminal"]["reputation"] = 9999
    bad["checksum"] = dig({k: v for k, v in bad.items() if k != "checksum"})
    with pytest.raises(SceneTravelError, match="replay"):
        verify_acceptance(bad, source=source)


@pytest.mark.parametrize("kwargs", [
    {"max_states": 0}, {"max_states": True},
    {"max_depth": 0}, {"max_depth": 129},
    {"ending_id": "unknown"},
])
def test_bad_budgets_and_unknown_ending_rejected(kwargs):
    with pytest.raises(SceneTravelError):
        accept_mission(original_mission(), **kwargs)


def test_cli_reaches_installed_app_and_verifies_report(capsys):
    from skeleton.__main__ import main
    assert main(["scene-mission-accept", "--demo", "--ending-id",
                 "lantern_restored", "--max-states", "512"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["accepted"] is True
    assert cli(["--demo", "--verify-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report


def test_cli_rejects_invalid_source(capsys):
    assert cli(["--source-json", '{"bad":true}']) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
