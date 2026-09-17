"""Keyed doors. Sequence puzzles. Extract stays locked until key path exists."""

from __future__ import annotations

from collections import deque
from typing import Any

from skeleton.game.labyrinth import adjacency


class LockError(ValueError):
    """Lock / key contract violation."""


def keys_in(graph: dict[str, Any]) -> list[str]:
    return [str(node["id"]) for node in graph.get("nodes") or [] if node.get("lock") or node.get("kind") == "lock"]


def open_with(graph: dict[str, Any], held: set[str]) -> dict[str, list[str]]:
    adj = adjacency(graph)
    locked = set(keys_in(graph))
    usable: dict[str, list[str]] = {node: [] for node in adj}
    for src, nbrs in adj.items():
        for dst in nbrs:
            if dst in locked and dst not in held and src not in held:
                continue
            usable[src].append(dst)
    return usable


def reach(usable: dict[str, list[str]], start: str, goal: str) -> bool:
    if start == goal:
        return True
    if start not in usable or goal not in usable:
        raise LockError("node missing")
    seen = {start}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        for nxt in usable[cur]:
            if nxt in seen:
                continue
            if nxt == goal:
                return True
            seen.add(nxt)
            queue.append(nxt)
    return False


def solve(graph: dict[str, Any]) -> dict[str, Any]:
    spawn = next(node["id"] for node in graph["nodes"] if node["kind"] == "spawn")
    extract = next(node["id"] for node in graph["nodes"] if node["kind"] == "extract")
    locked = keys_in(graph)
    held: set[str] = set()
    order: list[str] = []
    progress = True
    while progress:
        progress = False
        usable = open_with(graph, held)
        for key in locked:
            if key in held:
                continue
            if reach(usable, spawn, key):
                held.add(key)
                order.append(key)
                progress = True
    usable = open_with(graph, held)
    opened = reach(usable, spawn, extract)
    return {
        "kind": "lock_solve",
        "order": order,
        "held": sorted(held),
        "opened": opened,
        "extract": extract,
        "stored_prose": 0,
    }
