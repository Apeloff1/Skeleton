"""Replay-driven mission graph, source editing, earned endings and export integrity."""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import pytest

from skeleton.game.gameplay.ridge_rescue.custody import digest
from skeleton.game.gameplay.ridge_rescue.journal import open_journal, append_journal
from skeleton.game.gameplay.ridge_rescue.missions import (
    MissionError, parse_missions, evaluate_missions, revise_missions,
    verify_revision, export_missions, verify_export,
)
from skeleton.game.gameplay.ridge_rescue.schema import parse_world
from skeleton.game.gameplay.ridge_rescue.missions_cli import main

SOURCE = Path(__file__).parents[1] / "game" / "gameplay" / "ridge_rescue" / "cinder_ridge_missions.json"


def _source():
    return json.loads(SOURCE.read_text())


def _journal():
    return open_journal(parse_world(_source()["world"]))


def test_source_and_empty_journal():
    source = parse_missions(_source())
    result = evaluate_missions(source, _journal())
    assert result["score"] == 0
    assert len(result["earned"]) == len(source["nodes"])
    assert not result["chosen"]


def test_real_rescue_earns_first_node_and_score():
    journal = _journal()
    journal = append_journal(journal, {"verb": "move", "direction": "east"}, expected_head=journal["head"])
    journal = append_journal(journal, {"verb": "rescue", "target": "mira"}, expected_head=journal["head"])
    report = evaluate_missions(_source(), journal)
    earned = {n["id"]: n for n in report["earned"]}
    assert earned["mira_found"]["earned"]
    assert earned["mira_found"]["first_turn"] == 2
    assert earned["orin_found"]["earned"] is False
    assert report["score"] == 20


def test_tampered_journal_and_world_rejected():
    journal = _journal()
    forged = deepcopy(journal)
    forged["state"]["credits"] = 999
    with pytest.raises(MissionError, match="unreplayable"):
        evaluate_missions(_source(), forged)
    wrong = _source()
    wrong["world"]["name"] = "Forged Ridge"
    with pytest.raises(MissionError, match="does not match"):
        evaluate_missions(wrong, journal)


def test_dag_dependency_validation_and_no_duplicate_ids():
    source = _source()
    source["nodes"][0]["requires"] = ["salvage_exit"]
    with pytest.raises(MissionError, match="preceding"):
        parse_missions(source)
    source = _source()
    source["nodes"][1]["id"] = source["nodes"][0]["id"]
    with pytest.raises(MissionError, match="duplicate"):
        parse_missions(source)


def test_authoring_is_cas_protected_and_replay_verifiable():
    source = _source()
    operation = {"kind": "set-points", "id": "mira_found", "value": 25}
    revision = revise_missions(source, expected_sha256=digest(parse_missions(source)), operation=operation)
    assert revision["source"]["nodes"][0]["points"] == 25
    assert verify_revision(source, revision, operation)
    with pytest.raises(MissionError, match="stale"):
        revise_missions(source, expected_sha256="0" * 64, operation=operation)


def test_portable_mission_report_replays_and_rejects_tamper():
    bundle = export_missions(_source(), _journal())
    assert verify_export(json.dumps(bundle).encode())["score"] == 0
    forged = deepcopy(bundle)
    forged["payload"]["report"]["score"] = 100
    forged["sha256"] = digest(forged["payload"])
    with pytest.raises(MissionError, match="not earned"):
        verify_export(forged)


def test_cli_inspect_evaluate_export(tmp_path, capsys):
    assert main(["inspect", "--source", str(SOURCE)]) == 0
    assert json.loads(capsys.readouterr().out)["nodes"] == len(_source()["nodes"])
    path = tmp_path / "journal.json"
    path.write_text(json.dumps(_journal()))
    assert main(["evaluate", "--source", str(SOURCE), "--journal", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["score"] == 0
    export_path = tmp_path / "missions.json"
    assert main(["export", "--source", str(SOURCE), "--journal", str(path), "--output", str(export_path)]) == 0
    assert main(["verify", "--bundle", str(export_path)]) == 0
    assert json.loads(capsys.readouterr().out)["score"] == 0
