from __future__ import annotations

import json

import pytest

from skeleton.game.approval import ApprovalError, require, stamp
from skeleton.game.build_report import report
from skeleton.game.compose import compose
from skeleton.game.cut import CutError, cut, plan_sees
from skeleton.game.encounters import EncounterError, pack_tables, table
from skeleton.game.handoff import HandoffError, offer, resolve, session
from skeleton.game.provenance import ProvenanceError, meta
from skeleton.game.questionnaire import QuestionnaireError, fill
from skeleton.game.turn_engine import TurnEngineError, play


def test_turn_engine_twenty_ticks_warp_once() -> None:
    left = play(seed=8847291, ticks=20)
    right = play(seed=8847291, ticks=20)
    assert left["ticks"] == 20
    assert left["every_frame"] is False
    assert left["tokens"] == 5
    assert left["warp_count"] <= 1
    assert left["world_extract"] == 1
    assert left["passed"] is True
    assert left["stored_prose"] == 0
    assert left == right
    with pytest.raises(TurnEngineError):
        play(ticks=0)


def test_questionnaire_and_approval_boundary() -> None:
    sheet = fill("NEXUS-EXTRACT heat extract sleep godot #807")
    assert sheet["fields"]["loop"] == 1
    assert sheet["fields"]["emit"] == 1
    assert sheet["stored_prose"] == 0
    ok = stamp("NEXUS-EXTRACT heat extract #807", actor="operator", approve=True)
    assert ok["state"] == "approved"
    assert require(ok)["state"] == "approved"
    with pytest.raises(ApprovalError, match="conflicts"):
        stamp("godot unity extract #807", approve=True)
    with pytest.raises(QuestionnaireError):
        fill(" ")


def test_cut_plan_encounters_handoff_provenance_report() -> None:
    overlay = cut("heat_discipline")
    planned = plan_sees(overlay)
    assert planned["era"] == "heat_discipline"
    assert planned["reference"]["citation"] == "#807"
    with pytest.raises(CutError):
        cut("cyberpunk")
    pack = pack_tables(8847291)
    assert pack["n"] == 12
    assert table(seed=8847291, kind="hazard", n=4) == pack["tables"][1]
    with pytest.raises(EncounterError):
        table(seed=1, kind="loot", n=2)
    offered = offer(from_agent="a", to_agent="b", verb="offer")
    accepted = resolve(offered, "accept")
    mesh = session([offered, accepted])
    assert mesh["accepted"] == 1
    with pytest.raises(HandoffError):
        resolve(accepted, "accept")
    card = meta(path="data/catalog/encounters.json", seed=7, step="mass_forge", rotor="encounter")
    assert card["meta_path"].endswith(".meta.json")
    with pytest.raises(ProvenanceError):
        meta(path=".env", seed=1, step="export")
    exported = report(vision="NEXUS-EXTRACT #807", seed=8847291, forges=4)
    assert exported["sota_ready"] is False
    assert exported["digest"]
    assert report(vision="NEXUS-EXTRACT #807", seed=8847291, forges=4)["digest"] == exported["digest"]


def test_compose_seals_and_never_flips_ready() -> None:
    left = compose(seed=8847291)
    right = compose(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["sota_ready"] is False
    assert left["turn_passed"] is True
    assert left["conductor_ok"] is True
    assert left["retune"] is False
    assert left["stored_prose"] == 0
    assert left["law"] == "batch_complete_is_not_sota"
    assert len(left["release_root"]) == 64


def test_cli_turn_and_compose(capsys: pytest.CaptureFixture[str]) -> None:
    from skeleton.__main__ import main

    assert main(["turn", "--seed", "8847291"]) == 0
    turns = json.loads(capsys.readouterr().out)
    assert turns["ok"] is True
    assert turns["ticks"] == 20
    assert turns["sota_ready"] is False
    assert main(["compose", "--seed", "8847291"]) == 0
    sealed = json.loads(capsys.readouterr().out)
    assert sealed["ok"] is True
    assert sealed["sota_ready"] is False
    assert sealed["stored_prose"] == 0
