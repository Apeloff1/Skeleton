from __future__ import annotations

import json

from skeleton.game.campus_index import census, run_campus
from skeleton.game.cell_engine import run_cell
from skeleton.game.shafts import travel
from skeleton.game.status_pipe import apply_poison, tick_all
from skeleton.game.verb_laws import apply_verb


def test_census_sixteen_cells() -> None:
    card = census()
    assert card["n"] == 16
    assert card["stored_prose"] == 0


def test_extract_cell_once() -> None:
    run = run_cell(15, 8847291, ["heat", "heat", "extract", "extract"])
    assert run["final"]["kind"] == "extract"
    assert run["final"]["extracted"] == 1


def test_campus_run_sealed() -> None:
    left = run_campus(8847291)
    right = run_campus(8847291)
    assert left["digest"] == right["digest"]
    assert left["ok"] is True
    assert left["sota_ready"] is False
    assert left["floors"] == 4


def test_verbs_status_shafts() -> None:
    state = apply_verb({"heat": 10, "scrap": 2, "extracted": 0}, "scavenge")
    assert state["scrap"] >= 1
    unit = apply_poison({"hp": 20, "status": {}})
    unit = tick_all(unit)
    assert unit["hp"] <= 20
    moved = travel({"floor": 0, "extracted": 0, "coil": 1}, 1)
    assert moved["floor"] == 1


def test_cli_campus(capsys) -> None:
    from skeleton.__main__ import main

    assert main(["campus", "--seed", "8847291"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["sota_ready"] is False
