"""Pathfind on the multi-floor campus graph."""

from __future__ import annotations

from typing import Any

from skeleton.game.floors import weave_campus
from skeleton.game.pathfind import bfs, dijkstra


class FloorPathError(ValueError):
    pass


def route(*, seed: int, floors: int = 4, rooms: int = 8) -> dict[str, Any]:
    campus = weave_campus(seed=int(seed), floors=floors, rooms=rooms)
    spawn = next(n["id"] for n in campus["nodes"] if n["kind"] == "spawn")
    extract = next(n["id"] for n in campus["nodes"] if n["kind"] == "extract")
    path = bfs(campus, spawn, extract)
    weighted = dijkstra(campus, spawn, extract)
    if not path or path[0] != spawn or path[-1] != extract:
        raise FloorPathError("route")
    return {
        "kind": "floor_path",
        "seed": int(seed),
        "spawn": spawn,
        "extract": extract,
        "bfs": path,
        "dijkstra": weighted,
        "len": len(path),
        "stored_prose": 0,
    }
