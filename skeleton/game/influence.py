"""Influence map and flow field on a labyrinth / floor graph."""

from __future__ import annotations

from collections import deque
from typing import Any

from skeleton.game.labyrinth import adjacency


class InfluenceError(ValueError):
    pass


def seeds(graph: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in graph.get("nodes") or []:
        nid = str(node["id"])
        kind = str(node.get("kind") or "")
        score = int(node.get("heat") or 0)
        if kind == "extract":
            score += 8
        elif kind == "heat":
            score += 3
        elif kind == "lock":
            score -= 4
        elif kind == "spawn":
            score += 1
        out[nid] = score
    return out


def spread(graph: dict[str, Any], src: dict[str, int], steps: int = 4) -> dict[str, int]:
    if steps < 1 or steps > 16:
        raise InfluenceError("steps")
    adj = adjacency(graph)
    cur = {node: int(src.get(node, 0)) for node in adj}
    for _ in range(steps):
        nxt = dict(cur)
        for node, nbrs in adj.items():
            if not nbrs:
                continue
            avg = sum(cur[n] for n in nbrs) / len(nbrs)
            nxt[node] = int(round((cur[node] * 2 + avg) / 3))
        cur = nxt
    return cur


def flow(graph: dict[str, Any], goal: str) -> dict[str, str | None]:
    adj = adjacency(graph)
    if goal not in adj:
        raise InfluenceError("goal")
    prev: dict[str, str | None] = {goal: None}
    q = deque([goal])
    while q:
        cur = q.popleft()
        for nxt in adj[cur]:
            if nxt in prev:
                continue
            prev[nxt] = cur
            q.append(nxt)
    step: dict[str, str | None] = {node: None for node in adj}
    for node in adj:
        if node == goal:
            continue
        if node in prev and prev[node]:
            step[node] = prev[node]
    return step


def card(graph: dict[str, Any], goal: str) -> dict[str, Any]:
    base = seeds(graph)
    field = spread(graph, base, 4)
    arrows = flow(graph, goal)
    return {"kind": "influence", "field": field, "flow": arrows, "goal": goal, "stored_prose": 0}
