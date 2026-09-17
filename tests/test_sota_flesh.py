from __future__ import annotations

import json

from skeleton.game.climate import run as climate_run
from skeleton.game.encounters import run as enc_run
from skeleton.game.flesh_sim import play
from skeleton.game.floors import FloorError, weave_campus
from skeleton.game.skills import learn


def test_four_floors_one_extract() -> None:
    campus = weave_campus(seed=8847291, floors=4, rooms=8)
    assert campus["extracts"] == 1
    assert campus["floors"] == 4
    kinds = [n["kind"] for n in campus["nodes"]]
    assert kinds.count("extract") == 1
    assert kinds.count("spawn") == 1
    other = weave_campus(seed=17, floors=4, rooms=8)
    assert other["nodes"] != campus["nodes"] or other["edges"] != campus["edges"]


def test_climate_encounters_skills() -> None:
    campus = weave_campus(seed=8847291)
    weather = climate_run(campus["nodes"], ticks=8, phase="vent")
    assert weather["peak"] >= 0
    enc = enc_run("extract_gate", 8847291, ["enter", "extract"])
    assert enc["enc"] == "extract_gate"
    unit = learn({"xp": 10, "heat": 8, "skills": []}, "heat_ward")
    assert "heat_ward" in unit["skills"]


def test_flesh_sealed_and_extract_once() -> None:
    left = play(seed=8847291)
    right = play(seed=8847291)
    assert left["digest"] == right["digest"]
    assert left["extract_count"] == 1
    assert left["warp_count"] == 1
    assert left["sota_ready"] is False
    assert left["saved"] is True
    assert play(seed=3)["digest"] != left["digest"]


def test_cli_flesh(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["flesh", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
    assert payload["extract_count"] == 1
