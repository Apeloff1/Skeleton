"""Multi-floor labyrinth. Stairs, shafts, unique extract per campus."""

from __future__ import annotations

import hashlib
from collections import deque
from typing import Any

MAX_FLOORS = 4
MAX_ROOMS = 12
KINDS_MID = ("scavenge", "heat", "forge", "sleep", "dream", "lock")


class FloorError(ValueError):
    pass


def _roll(seed: int, label: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}:fl".encode()).digest()[:8], "big")


def weave_floor(floor: int, *, seed: int, rooms: int = 8) -> dict[str, Any]:
    if rooms < 4 or rooms > MAX_ROOMS:
        raise FloorError("rooms")
    if floor < 0 or floor >= MAX_FLOORS:
        raise FloorError("floor")
    nodes = []
    edges = []
    seen: set[tuple[str, str]] = set()
    for i in range(rooms):
        if i == 0 and floor == 0:
            kind = "spawn"
        elif i == rooms - 1 and floor == MAX_FLOORS - 1:
            kind = "extract"
        elif i == rooms - 1:
            kind = "stair"
        else:
            kind = KINDS_MID[_roll(seed, f"k:{floor}:{i}") % len(KINDS_MID)]
        nodes.append({
            "id": f"f{floor}r{i}",
            "floor": floor,
            "kind": kind,
            "heat": _roll(seed, f"h:{floor}:{i}") % 8,
            "lock": kind == "lock",
        })

    def link(a: int, b: int) -> None:
        if a == b or not (0 <= a < rooms and 0 <= b < rooms):
            return
        pair = (f"f{floor}r{min(a, b)}", f"f{floor}r{max(a, b)}")
        if pair in seen:
            return
        seen.add(pair)
        edges.append({"from": f"f{floor}r{a}", "to": f"f{floor}r{b}"})
        edges.append({"from": f"f{floor}r{b}", "to": f"f{floor}r{a}"})

    for i in range(rooms - 1):
        link(i, i + 1)
    for i in range(rooms - 2):
        if _roll(seed, f"ch:{floor}:{i}") % 3 == 0:
            link(i, i + 2)
    return {"kind": "floor", "floor": floor, "seed": int(seed), "nodes": nodes, "edges": edges, "stored_prose": 0}


def weave_floor_0(*, seed: int, rooms: int = 8) -> dict[str, Any]:
    return weave_floor(0, seed=seed, rooms=rooms)


def weave_floor_1(*, seed: int, rooms: int = 8) -> dict[str, Any]:
    return weave_floor(1, seed=seed, rooms=rooms)


def weave_floor_2(*, seed: int, rooms: int = 8) -> dict[str, Any]:
    return weave_floor(2, seed=seed, rooms=rooms)


def weave_floor_3(*, seed: int, rooms: int = 8) -> dict[str, Any]:
    return weave_floor(3, seed=seed, rooms=rooms)


def weave_campus(*, seed: int, floors: int = 4, rooms: int = 8) -> dict[str, Any]:
    if floors < 2 or floors > MAX_FLOORS:
        raise FloorError("floors")
    layers = [weave_floor(fl, seed=seed, rooms=rooms) for fl in range(floors)]
    shafts = []
    for fl in range(floors - 1):
        a = f"f{fl}r{rooms-1}"
        b = f"f{fl+1}r0"
        shafts.append({"from": a, "to": b})
        shafts.append({"from": b, "to": a})
    nodes = [n for layer in layers for n in layer["nodes"]]
    edges = [e for layer in layers for e in layer["edges"]] + shafts
    extracts = [n["id"] for n in nodes if n["kind"] == "extract"]
    spawns = [n["id"] for n in nodes if n["kind"] == "spawn"]
    if len(extracts) != 1 or len(spawns) != 1:
        raise FloorError("extract/spawn contract")
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        adj[e["from"]].append(e["to"])
    seen = {spawns[0]}
    q = deque([spawns[0]])
    while q:
        cur = q.popleft()
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                q.append(nxt)
    if extracts[0] not in seen:
        raise FloorError("extract unreachable")
    return {
        "kind": "campus_floors",
        "seed": int(seed),
        "floors": floors,
        "nodes": nodes,
        "edges": edges,
        "shafts": len(shafts) // 2,
        "extracts": 1,
        "reachable": len(seen),
        "stored_prose": 0,
    }


def card(seed: int) -> dict[str, Any]:
    g = weave_campus(seed=seed)
    return {"kind": "floors_card", "floors": g["floors"], "nodes": len(g["nodes"]), "extracts": 1, "stored_prose": 0}
