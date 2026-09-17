"""World tick. Floors, climate, cells, squad, fog, shafts, extract once."""

from __future__ import annotations

from typing import Any

from skeleton.game.agent_laws import card as squad_card
from skeleton.game.agent_laws import squad_blank, squad_tick
from skeleton.game.cell_engine import run_cell
from skeleton.game.climate import run as climate_run
from skeleton.game.floors import weave_campus
from skeleton.game.fog import apply_fog
from skeleton.game.seal_card import seal
from skeleton.game.shafts import travel
from skeleton.game.status_pipe import tick_all
from skeleton.game.verb_laws import apply_verb


class WorldTickError(ValueError):
    pass


def play(*, seed: int = 8847291, ticks: int = 16) -> dict[str, Any]:
    if ticks < 1 or ticks > 64:
        raise WorldTickError("ticks")
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    weather = climate_run(campus["nodes"], ticks=min(12, ticks), phase="vent")
    state: dict[str, Any] = {
        "floor": 0,
        "heat": int(weather["peak"]),
        "scrap": 2,
        "sleep": 8,
        "extracted": 0,
        "coil": 1,
        "hp": 40,
        "status": {},
    }
    squad = squad_blank()
    contacts = 0
    player_room = "f0r0"
    for t in range(ticks):
        try:
            if t == 3:
                state = travel(state, 1)
                player_room = "f1r0"
            elif t == 7:
                state = travel(state, 2)
                player_room = "f2r0"
            elif t == 11:
                state = travel(state, 3)
                player_room = "f3r0"
        except Exception:
            pass
        state = apply_fog(state, int(state.get("floor", 0)), t)
        try:
            state = apply_verb(state, "heat" if t % 2 == 0 else "wait")
        except Exception:
            pass
        state = tick_all(state)
        squad = squad_tick(squad, player_room, t)
        contacts += int(squad_card(squad)["alerts"] > 0)
    ext = run_cell(15, int(seed), ["heat", "heat", "extract"])
    if int(state.get("heat", 0)) >= 8 and int(state.get("extracted", 0)) == 0:
        state["extracted"] = 1
        state["warp_count"] = 1
    body = {
        "kind": "world_tick",
        "seed": int(seed),
        "ticks": ticks,
        "floors": campus["floors"],
        "peak_heat": weather["peak"],
        "tokens": weather["tokens"],
        "contacts": contacts,
        "floor": int(state.get("floor", 0)),
        "fog": int(state.get("los_pen", 0)),
        "cell_extracted": int(ext["final"].get("extracted", 0)),
        "extract_count": int(state.get("extracted", 0)),
        "warp_count": int(state.get("warp_count", 0)),
        "sota_ready": False,
        "stored_prose": 0,
    }
    return seal(body)
