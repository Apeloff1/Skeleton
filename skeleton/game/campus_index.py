"""Campus index. Sixteen room engines plus verb laws, hazards, squad."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from skeleton.game.agent_laws import card as squad_card
from skeleton.game.agent_laws import squad_blank, squad_tick
from skeleton.game.hazard_laws import pulse_room
from skeleton.game.seal_card import seal
from skeleton.game.tile_engine import campus_tick
from skeleton.game.verb_laws import run_script


ROOMS = tuple(f"skeleton.game.room_{i:02d}" for i in range(16))


class CampusIndexError(ValueError):
    pass


def load(index: int):
    if index < 0 or index > 15:
        raise CampusIndexError("index")
    return import_module(ROOMS[index])


def census() -> dict[str, Any]:
    rows = []
    for i, name in enumerate(ROOMS):
        mod = import_module(name)
        rows.append({"id": mod.ROOM_ID, "kind": mod.KIND, "tiles": mod.card()["tiles"]})
    return {"kind": "campus_index", "n": len(rows), "rooms": rows, "stored_prose": 0}


def run_campus(seed: int) -> dict[str, Any]:
    verbs = {
        0: ["heat", "move", "wait"],
        1: ["scavenge", "heat", "wait"],
        15: ["heat", "heat", "extract"],
    }
    ticks = campus_tick(seed, verbs)
    script = run_script({"heat": 10, "scrap": 2, "sleep": 8}, ["heat", "scavenge", "craft", "extract"])
    squad = squad_blank()
    for t in range(8):
        squad = squad_tick(squad, "r15" if t > 5 else "r0", t)
    alerts = squad_card(squad)
    room0 = load(0).blank(seed)
    room0 = pulse_room(room0, 0, 3)
    body = {
        "kind": "campus_run",
        "seed": int(seed),
        "rooms": ticks["n"],
        "script_n": script["n"],
        "alerts": alerts["alerts"],
        "pulsed_heat": int(room0.get("heat", 0)),
        "sota_ready": False,
        "stored_prose": 0,
        "ok": True,
    }
    return seal(body)


def tour(seed: int) -> dict[str, Any]:
    frames = []
    extracted = 0
    for index in range(16):
        mod = load(index)
        verbs = ["heat", "wait"]
        if mod.KIND == "scavenge":
            verbs = ["scavenge", "heat"]
        elif mod.KIND == "extract":
            verbs = ["heat", "heat", "extract"]
        elif mod.KIND == "lock":
            verbs = ["unlock", "enter"]
        elif mod.KIND == "dream":
            verbs = ["dream", "wake"]
        elif mod.KIND == "sleep":
            verbs = ["sleep", "dream"]
        elif mod.KIND == "forge":
            verbs = ["scavenge", "wait"]
        run = getattr(mod, f"run_{index:02d}")(seed, verbs)
        final = run["final"]
        extracted = int(final.get("extracted", 0))
        frames.append({"id": mod.ROOM_ID, "kind": mod.KIND, "heat": int(final.get("heat", 0)), "extracted": extracted})
    return seal({
        "kind": "campus_tour",
        "seed": int(seed),
        "n": len(frames),
        "frames": frames,
        "extracted": extracted,
        "sota_ready": False,
        "stored_prose": 0,
    })
