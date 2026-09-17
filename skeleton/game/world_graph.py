"""Deterministic place+prefill door graph. No galaxy fork. Warp extracts once."""

from __future__ import annotations

import hashlib
from typing import Any


MAX_ROOMS = 8
ROOM_KINDS = ("spawn", "scavenge", "heat", "forge", "extract")


class WorldGraphError(ValueError):
    """World graph contract violation."""


def _roll(seed: int, label: str) -> int:
    material = f"{int(seed)}:{label}:world".encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def place(*, seed: int, rooms: int = 5) -> dict[str, Any]:
    if isinstance(rooms, bool) or not isinstance(rooms, int):
        raise WorldGraphError("rooms must be an integer")
    if rooms < 2 or rooms > MAX_ROOMS:
        raise WorldGraphError("rooms out of N-cap")
    nodes = []
    for index in range(rooms):
        if index == 0:
            kind = "spawn"
        elif index == rooms - 1:
            kind = "extract"
        else:
            kind = ROOM_KINDS[1 + (_roll(seed, f"kind:{index}") % 3)]
        nodes.append({"id": f"r{index}", "kind": kind, "heat": _roll(seed, f"heat:{index}") % 8})
    edges = []
    for index in range(rooms - 1):
        edges.append({"from": f"r{index}", "to": f"r{index + 1}"})
        if rooms > 3 and _roll(seed, f"side:{index}") % 3 == 0 and index + 2 < rooms:
            edges.append({"from": f"r{index}", "to": f"r{index + 2}"})
    return {
        "kind": "world_graph",
        "seed": int(seed),
        "nodes": nodes,
        "edges": edges,
        "domains": sorted({node["kind"] for node in nodes}),
        "stored_prose": 0,
    }


def walk(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph.get("nodes") or []}
    if "r0" not in nodes or nodes["r0"]["kind"] != "spawn":
        raise WorldGraphError("graph missing spawn")
    extract_ids = [node["id"] for node in nodes.values() if node["kind"] == "extract"]
    if not extract_ids:
        raise WorldGraphError("graph missing extract")
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in graph.get("edges") or []:
        adjacency[str(edge["from"])].append(str(edge["to"]))
    path = ["r0"]
    seen = {"r0"}
    current = "r0"
    extracted = 0
    while current not in extract_ids:
        nxt = next((item for item in adjacency[current] if item not in seen), None)
        if nxt is None:
            raise WorldGraphError("walk dead-ends before extract")
        path.append(nxt)
        seen.add(nxt)
        current = nxt
    extracted = 1
    return {
        "kind": "world_walk",
        "path": path,
        "hops": len(path) - 1,
        "extracted": extracted,
        "warp_count": extracted,
        "extract_count": extracted,
        "passed": extracted == 1,
        "stored_prose": 0,
    }
