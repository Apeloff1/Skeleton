"""Playable circuit production acceptance, adversarial receipts and CLI."""
import copy
import json

import pytest

from skeleton.__main__ import main
from skeleton.game.gameplay.scene_circuit import (
    original_circuit, simulate_circuit, verify_circuit,
)
from skeleton.game.gameplay.scene_circuit_accept import (
    SCHEMA, accept_circuit, cli, verify_acceptance,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_end_to_end_author_route_save_export_and_import():
    source, _ = original_circuit()
    original = copy.deepcopy(source)
    report = accept_circuit(source)
    assert source == original
    assert report["schema_version"] == SCHEMA
    assert report["phase"] == "won"
    assert report["plan"]["status"] == "found"
    assert report["terminal"]["state"]["scene"]["state"]["phase"] == "won"
    assert report["checkpoint"]["state"]["tick"] < report["terminal"]["state"]["tick"]
    assert report["portable"]["session"] == report["terminal"]
    assert report["terminal"]["state_digest"] == report["plan"]["final_state_digest"]
    assert verify_acceptance(json.loads(json.dumps(report))) == report


def test_editor_changes_are_proven_in_playable_preview():
    source, _ = original_circuit()
    edits = [{"kind": "set_initial", "switch_id": "quay_lantern",
              "initial_on": True}]
    original = copy.deepcopy(source)
    report = accept_circuit(source, edits)
    assert source == original
    assert next(s for s in report["terminal"]["source"]["switches"]
                if s["id"] == "quay_lantern")["initial_on"] is True
    assert report["terminal"]["state"]["scene"]["state"]["phase"] == "won"
    assert len(report["plan"]["actions"]) == 3
    assert verify_acceptance(report) == report


def test_unreachable_and_budget_exhaustion_never_certified():
    source, _ = original_circuit()
    with pytest.raises(SceneTravelError, match="inconclusive"):
        accept_circuit(source, max_states=1)
    with pytest.raises(SceneTravelError, match="inconclusive"):
        accept_circuit(source, max_depth=1)
    next(s for s in source["world"]["scenes"]
         if s["id"] == "gate")["exits"][0]["to"] = "sinkhole"
    with pytest.raises(SceneTravelError, match="unreachable"):
        accept_circuit(source)


@pytest.mark.parametrize("tamper", [
    lambda r: r.update(receipt="0" * 64),
    lambda r: r["plan"].update(status="unreachable"),
    lambda r: r["checkpoint"]["state"]["switches"].update(quay_lantern=False),
    lambda r: r["terminal"]["state"]["scene"]["state"].update(scene_id="quay"),
    lambda r: r["portable"].update(session_digest="0" * 64),
    lambda r: r["edits"].append({"kind": "set_initial",
                                "switch_id": "quay_lantern", "initial_on": True}),
    lambda r: r.update(source_digest="0" * 64),
    lambda r: r.update(phase="lost"),
])
def test_tampered_acceptance_fails_closed(tamper):
    source, _ = original_circuit()
    report = accept_circuit(source)
    before = copy.deepcopy(report)
    tamper(report)
    assert report != before
    with pytest.raises(SceneTravelError):
        verify_acceptance(report)


def test_invalid_source_and_edit_cannot_publish_report():
    source, _ = original_circuit()
    with pytest.raises(SceneTravelError):
        accept_circuit(source, [{"kind": "set_initial", "switch_id": "missing",
                                 "initial_on": True}])
    with pytest.raises(SceneTravelError):
        accept_circuit(source, [1])
    with pytest.raises(SceneTravelError):
        verify_acceptance({"schema_version": SCHEMA})


def test_cli_and_canonical_dispatch(capsys):
    source, _ = original_circuit()
    assert cli(["demo"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["phase"] == "won"
    assert cli(["verify", "--report-json", json.dumps(report)]) == 0
    assert json.loads(capsys.readouterr().out) == report
    assert main(["scene-circuit-accept", "check",
                 "--source-json", json.dumps(source)]) == 0
    assert json.loads(capsys.readouterr().out)["phase"] == "won"
    assert cli(["check", "--source-json", "{}"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
