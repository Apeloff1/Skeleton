"""Room occupancy, jam, and spill across campus floors."""

from __future__ import annotations

from typing import Any

from skeleton.game.floors import weave_campus
from skeleton.game.seal_card import seal


class OccupancyError(ValueError):
    pass


CAP = {"spawn": 4, "extract": 2, "heat": 6, "lock": 2, "empty": 8, "stair": 3}


def capacities(graph: dict[str, Any]) -> dict[str, int]:
    out = {}
    for node in graph.get("nodes") or []:
        kind = str(node.get("kind") or "empty")
        out[str(node["id"])] = int(CAP.get(kind, 4))
    return out


def blank(graph: dict[str, Any]) -> dict[str, int]:
    return {str(n["id"]): 0 for n in graph.get("nodes") or []}


def enter(count: dict[str, int], cap: dict[str, int], room: str, n: int = 1) -> dict[str, int]:
    if room not in count:
        raise OccupancyError("room")
    nxt = dict(count)
    nxt[room] = int(nxt[room]) + int(n)
    if nxt[room] > cap.get(room, 4):
        raise OccupancyError("jam")
    if nxt[room] < 0:
        raise OccupancyError("empty")
    return nxt


def spill(count: dict[str, int], cap: dict[str, int], edges: list[dict[str, Any]]) -> dict[str, int]:
    nxt = dict(count)
    for edge in edges:
        src = str(edge.get("from") or "")
        dst = str(edge.get("to") or "")
        if src not in nxt or dst not in nxt:
            continue
        extra = nxt[src] - cap.get(src, 4)
        if extra <= 0:
            continue
        room = cap.get(dst, 4) - nxt[dst]
        move = min(extra, max(0, room))
        nxt[src] -= move
        nxt[dst] += move
    return nxt


def play(*, seed: int = 8847291, ticks: int = 12) -> dict[str, Any]:
    campus = weave_campus(seed=int(seed), floors=4, rooms=8)
    cap = capacities(campus)
    count = blank(campus)
    spawn = next(n["id"] for n in campus["nodes"] if n["kind"] == "spawn")
    extract = next(n["id"] for n in campus["nodes"] if n["kind"] == "extract")
    jams = 0
    count = enter(count, cap, spawn, 3)
    for t in range(ticks):
        try:
            if t % 2 == 0:
                count = enter(count, cap, spawn, 1)
        except OccupancyError:
            jams += 1
        count = spill(count, cap, list(campus.get("edges") or []))
    return seal({
        "kind": "occupancy",
        "seed": int(seed),
        "pop": sum(count.values()),
        "jams": jams,
        "extract_load": count.get(extract, 0),
        "sota_ready": False,
        "stored_prose": 0,
    })
