"""World tick. Floors, climate, path, craft, influence, events, extract once."""

from __future__ import annotations

from typing import Any

from skeleton.game.agent_laws import card as squad_card
from skeleton.game.agent_laws import squad_blank, squad_tick
from skeleton.game.cell_engine import run_cell
from skeleton.game.climate import run as climate_run
from skeleton.game.craft_inv import kit
from skeleton.game.floor_path import route
from skeleton.game.floors import weave_campus
from skeleton.game.fog import apply_fog
from skeleton.game.influence import card as influence_card
from skeleton.game.seal_card import seal
from skeleton.game.shafts import travel
from skeleton.game.status_pipe import tick_all
from skeleton.game.verb_laws import apply_verb
from skeleton.game.world_events import run as event_run


class WorldTickError(ValueError):
    pass


def play(*, seed: int = 8847291, ticks: int = 16) -> dict[str, Any]:
    if ticks < 1 or ticks > 64:
        raise WorldTickError("ticks")
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    weather = climate_run(campus["nodes"], ticks=min(12, ticks), phase="vent")
    path = route(seed=int(seed), floors=4, rooms=8)
    extract = path["extract"]
    field = influence_card(campus, extract)
    bag = kit(int(seed))
    ev = event_run("extract_hum", int(seed), 3)
    state: dict[str, Any] = {
        "floor": 0,
        "heat": int(weather["peak"]),
        "scrap": 2,
        "sleep": 8,
        "extracted": 0,
        "coil": int(bag["slots"].get("coil") or 0),
        "hp": 40,
        "status": {},
    }
    squad = squad_blank()
    contacts = 0
    player_room = path["bfs"][0] if path["bfs"] else "f0r0"
    hops = path["bfs"]
    for t in range(ticks):
        if hops:
            player_room = hops[min(t, len(hops) - 1)]
            if player_room.startswith("f") and len(player_room) >= 2 and player_room[1].isdigit():
                state["floor"] = int(player_room[1])
        try:
            dest = int(state.get("floor", 0))
            if t == 3:
                state = travel(state, min(3, dest + 1))
            elif t == 7:
                state = travel(state, min(3, int(state.get("floor", 0)) + 1))
            elif t == 11:
                state = travel(state, 3)
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
        "path_len": path["len"],
        "flow_goal": field["goal"],
        "coil": bag["slots"]["coil"],
        "event": ev["event"],
        "cell_extracted": int(ext["final"].get("extracted", 0)),
        "extract_count": int(state.get("extracted", 0)),
        "warp_count": int(state.get("warp_count", 0)),
        "sota_ready": False,
        "stored_prose": 0,
    }
    return seal(body)
