"""Dream warp. Mutate a copy of the labyrinth, then snap back. Extract stays unique."""

from __future__ import annotations

from typing import Any

from skeleton.game.labyrinth import LabyrinthError, adjacency, analyze, weave


class DreamWarpError(ValueError):
    """Dream warp contract violation."""


def mutate(graph: dict[str, Any], *, seed: int) -> dict[str, Any]:
    nodes = [dict(node) for node in graph.get("nodes") or []]
    edges = [dict(edge) for edge in graph.get("edges") or []]
    if not nodes:
        raise DreamWarpError("empty graph")
    flipped = 0
    for node in nodes:
        if node["kind"] in {"scavenge", "heat", "forge", "sleep"}:
            node["heat"] = (int(node["heat"]) + (seed % 3)) % 8
            flipped += 1
    dreamt = {
        "kind": "dream_graph",
        "seed": int(seed),
        "nodes": nodes,
        "edges": edges,
        "flipped": flipped,
        "stored_prose": 0,
    }
    report = analyze(dreamt)
    if report["extracts"] != 1:
        raise DreamWarpError("dream broke extract uniqueness")
    dreamt["reachable"] = report["reachable"]
    return dreamt


def session(*, seed: int, rooms: int = 8) -> dict[str, Any]:
    base = weave(seed=seed, rooms=rooms)
    night = mutate(base, seed=seed + 17)
    wake = weave(seed=seed, rooms=rooms)
    if wake["edges"] != base["edges"]:
        raise DreamWarpError("wake did not snap")
    adj = adjacency(wake)
    if not adj:
        raise LabyrinthError("empty wake")
    return {
        "kind": "dream_warp",
        "seed": int(seed),
        "base_cycles": base["cycles"],
        "dream_flipped": night["flipped"],
        "snapped": True,
        "extracts": 1,
        "stored_prose": 0,
    }
