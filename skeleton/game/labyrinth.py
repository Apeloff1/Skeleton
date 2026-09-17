"""Labyrinth topology. Cycles, dead-ends, bridges, unique extract."""

from __future__ import annotations

import hashlib
from collections import deque
from typing import Any


MAX_ROOMS = 16
KINDS = ("spawn", "scavenge", "heat", "forge", "sleep", "dream", "lock", "extract")


class LabyrinthError(ValueError):
    """Labyrinth contract violation."""


def _roll(seed: int, label: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}:lab".encode("utf-8")).digest()[:8], "big")


def weave(*, seed: int, rooms: int = 8) -> dict[str, Any]:
    if rooms < 4 or rooms > MAX_ROOMS:
        raise LabyrinthError("rooms out of range")
    nodes = []
    for index in range(rooms):
        if index == 0:
            kind = "spawn"
        elif index == rooms - 1:
            kind = "extract"
        else:
            kind = KINDS[1 + (_roll(seed, f"k:{index}") % (len(KINDS) - 2))]
        nodes.append({
            "id": f"r{index}",
            "kind": kind,
            "heat": _roll(seed, f"h:{index}") % 8,
            "lock": kind == "lock",
        })
    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def link(a: int, b: int) -> None:
        if a == b or not (0 <= a < rooms and 0 <= b < rooms):
            return
        pair = (f"r{min(a, b)}", f"r{max(a, b)}")
        if pair in seen:
            return
        seen.add(pair)
        edges.append({"from": f"r{a}", "to": f"r{b}"})
        edges.append({"from": f"r{b}", "to": f"r{a}"})

    for index in range(rooms - 1):
        link(index, index + 1)
    for index in range(rooms - 2):
        if _roll(seed, f"chord:{index}") % 3 == 0:
            link(index, index + 2)
    if rooms >= 6 and _roll(seed, "loop") % 2 == 0:
        link(1, rooms - 2)
    graph = {"kind": "labyrinth", "seed": int(seed), "nodes": nodes, "edges": edges, "stored_prose": 0}
    report = analyze(graph)
    if report["extracts"] != 1 or not report["spawn_reaches_extract"]:
        raise LabyrinthError("labyrinth extract contract failed")
    graph["cycles"] = report["cycles"]
    graph["dead_ends"] = report["dead_ends"]
    graph["bridges"] = report["bridges"]
    return graph


def adjacency(graph: dict[str, Any]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {str(node["id"]): [] for node in graph.get("nodes") or []}
    for edge in graph.get("edges") or []:
        src, dst = str(edge["from"]), str(edge["to"])
        if src not in adj or dst not in adj:
            raise LabyrinthError("dangling edge")
        if dst not in adj[src]:
            adj[src].append(dst)
    return adj


def analyze(graph: dict[str, Any]) -> dict[str, Any]:
    adj = adjacency(graph)
    nodes = list(adj)
    extracts = [node["id"] for node in graph["nodes"] if node["kind"] == "extract"]
    spawns = [node["id"] for node in graph["nodes"] if node["kind"] == "spawn"]
    if len(spawns) != 1:
        raise LabyrinthError("need one spawn")
    seen: set[str] = set()
    queue = deque(spawns)
    seen.add(spawns[0])
    while queue:
        cur = queue.popleft()
        for nxt in adj[cur]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    dead = [node for node in nodes if node not in extracts and node not in spawns and len(adj[node]) <= 1]
    bridges = _bridges(adj)
    cycles = _cycle_count(adj)
    return {
        "kind": "labyrinth_analysis",
        "extracts": len(extracts),
        "spawn_reaches_extract": bool(extracts) and extracts[0] in seen,
        "reachable": len(seen),
        "dead_ends": dead,
        "bridges": bridges,
        "cycles": cycles,
        "stored_prose": 0,
    }


def _bridges(adj: dict[str, list[str]]) -> list[list[str]]:
    time = 0
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    found: list[list[str]] = []

    def walk(u: str) -> None:
        nonlocal time
        disc[u] = low[u] = time
        time += 1
        for v in adj[u]:
            if v not in disc:
                parent[v] = u
                walk(v)
                low[u] = min(low[u], low[v])
                if low[v] > disc[u]:
                    found.append(sorted([u, v]))
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    for node in adj:
        if node not in disc:
            parent[node] = None
            walk(node)
    return found


def _cycle_count(adj: dict[str, list[str]]) -> int:
    v = len(adj)
    e = sum(len(nbrs) for nbrs in adj.values()) // 2
    comps = 0
    seen: set[str] = set()
    for node in adj:
        if node in seen:
            continue
        comps += 1
        stack = [node]
        seen.add(node)
        while stack:
            cur = stack.pop()
            for nxt in adj[cur]:
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
    return max(0, e - v + comps)
