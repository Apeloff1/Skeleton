"""Atomic scene circuit authoring, preview, edit validation and receipts."""
import copy
import json

import pytest

from skeleton.game.gameplay.scene_circuit import original_circuit
from skeleton.game.gameplay.scene_circuit_author import (
    SCHEMA, author_circuit, cli, verify_author_report,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError


def test_edit_switch_and_preview_playable_victory():
    source, _ = original_circuit()
    edits = [{"kind": "set_initial", "switch_id": "quay_lantern",
              "initial_on": True}]
    report = author_circuit(source, edits)
    assert next(s for s in report["source"]["switches"]
                if s["id"] == "quay_lantern")["initial_on"] is True
    assert report["preview"]["status"] == "found"
    assert verify_author_report(json.loads(json.dumps(report))) == report
    assert next(s for s in source["switches"]
                if s["id"] == "quay_lantern")["initial_on"] is False


def test_add_switch_then_rewire_gate_atomically():
    source, _ = original_circuit()
    edits = [
        {"kind": "add_switch", "switch": {
            "id": "beacon", "scene_id": "quay", "initial_on": True,
        }},
        {"kind": "set_gate", "scene_id": "quay", "exit_id": "north",
         "requires_on": ["beacon"], "requires_off": []},
        {"kind": "remove_switch", "switch_id": "quay_lantern"},
    ]
    report = author_circuit(source, edits)
    assert "beacon" in [x["id"] for x in report["source"]["switches"]]
    assert report["preview"]["status"] == "found"


@pytest.mark.parametrize("edits", [
    [{"kind": "remove_switch", "switch_id": "quay_lantern"}],
    [{"kind": "set_initial", "switch_id": "quay_lantern", "initial_on": 1}],
    [{"kind": "add_gate", "gate": {
        "scene_id": "quay", "exit_id": "north",
        "requires_on": ["quay_lantern"], "requires_off": [],
    }}],
    [{"kind": "remove_gate", "scene_id": "quay", "exit_id": "missing"}],
    [{"kind": "set_gate", "scene_id": "quay", "exit_id": "north",
      "requires_on": ["missing"], "requires_off": []}],
])
def test_invalid_edit_batch_fails_without_source_mutation(edits):
    source, _ = original_circuit()
    prior = copy.deepcopy(source)
    with pytest.raises(SceneTravelError):
        author_circuit(source, edits)
    assert source == prior


def test_tampered_report_cannot_certify():
    source, _ = original_circuit()
    report = author_circuit(source, [])
    report["preview"]["status"] = "unreachable"
    with pytest.raises(SceneTravelError):
        verify_author_report(report)


def test_cli_demo_and_error(capsys):
    assert cli(["demo"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == SCHEMA
    assert cli(["patch", "--source-json", "{}", "--edits-json", "[]"]) == 2
    assert json.loads(capsys.readouterr().err)["ok"] is False
