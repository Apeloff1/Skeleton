"""Campus index. Floors + cells + squad + verbs. No missing room_* imports."""

from __future__ import annotations

from typing import Any

from skeleton.game.agent_laws import card as squad_card
from skeleton.game.agent_laws import squad_blank, squad_tick
from skeleton.game.cell_engine import census as cell_census
from skeleton.game.cell_engine import tour as cell_tour
from skeleton.game.climate import run as climate_run
from skeleton.game.floors import weave_campus
from skeleton.game.fog import apply_fog
from skeleton.game.seal_card import seal
from skeleton.game.shafts import travel
from skeleton.game.verb_laws import run_script


class CampusIndexError(ValueError):
    pass


def census() -> dict[str, Any]:
    cells = cell_census()
    return {"kind": "campus_index", "n": cells["n"], "rooms": cells["cells"], "stored_prose": 0}


def run_campus(seed: int) -> dict[str, Any]:
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    weather = climate_run(campus["nodes"], ticks=12, phase="vent")
    script = run_script({"heat": 10, "scrap": 2, "sleep": 8}, ["heat", "scavenge", "craft", "extract"])
    squad = squad_blank()
    for t in range(8):
        squad = squad_tick(squad, "f3r3" if t > 5 else "f0r0", t)
    alerts = squad_card(squad)
    state = {"floor": 0, "heat": weather["peak"], "extracted": 0, "coil": 1}
    state = apply_fog(state, 0, 3)
    try:
        state = travel(state, 1)
        state = travel(state, 2)
        state = travel(state, 3)
    except Exception:
        pass
    walked = cell_tour(int(seed))
    body = {
        "kind": "campus_run",
        "seed": int(seed),
        "rooms": campus["floors"] * 8,
        "floors": campus["floors"],
        "script_n": script["n"],
        "alerts": alerts["alerts"],
        "pulsed_heat": weather["peak"],
        "fog": int(state.get("los_pen", 0)),
        "floor": int(state.get("floor", 0)),
        "tour_extracted": walked.get("extracted", 0),
        "sota_ready": False,
        "stored_prose": 0,
        "ok": True,
    }
    return seal(body)


def tour(seed: int) -> dict[str, Any]:
    return seal(cell_tour(int(seed)))
