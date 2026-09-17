"""Door-graph pathfinding. BFS + Dijkstra. Extract route is unique-once."""

from __future__ import annotations

from collections import deque
from typing import Any, Mapping


class PathfindError(ValueError):
    """Pathfinding contract violation."""


def adjacency(graph: Mapping[str, Any]) -> dict[str, list[str]]:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    if not nodes:
        raise PathfindError("graph has no nodes")
    adj: dict[str, list[str]] = {str(node["id"]): [] for node in nodes}
    for edge in edges:
        src = str(edge.get("from") or "")
        dst = str(edge.get("to") or "")
        if src not in adj or dst not in adj:
            raise PathfindError("edge references missing node")
        if dst not in adj[src]:
            adj[src].append(dst)
    return adj


def bfs(graph: Mapping[str, Any], start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]
    adj = adjacency(graph)
    if start not in adj or goal not in adj:
        raise PathfindError("start or goal missing")
    queue: deque[str] = deque([start])
    prev: dict[str, str | None] = {start: None}
    while queue:
        cur = queue.popleft()
        for nxt in adj[cur]:
            if nxt in prev:
                continue
            prev[nxt] = cur
            if nxt == goal:
                queue.clear()
                break
            queue.append(nxt)
    if goal not in prev:
        raise PathfindError("no path")
    path = [goal]
    while path[-1] != start:
        parent = prev[path[-1]]
        if parent is None:
            break
        path.append(parent)
    path.reverse()
    return path


def dijkstra(graph: Mapping[str, Any], start: str, goal: str) -> dict[str, Any]:
    adj = adjacency(graph)
    heat = {str(node["id"]): int(node.get("heat") or 0) for node in graph.get("nodes") or []}
    if start not in adj or goal not in adj:
        raise PathfindError("start or goal missing")
    dist = {node: 10**9 for node in adj}
    dist[start] = 0
    prev: dict[str, str | None] = {start: None}
    seen: set[str] = set()
    while len(seen) < len(adj):
        cand = None
        best = 10**9
        for node, cost in dist.items():
            if node not in seen and cost < best:
                best = cost
                cand = node
        if cand is None:
            break
        seen.add(cand)
        if cand == goal:
            break
        for nxt in adj[cand]:
            step = 1 + heat.get(nxt, 0)
            alt = dist[cand] + step
            if alt < dist[nxt]:
                dist[nxt] = alt
                prev[nxt] = cand
    if dist[goal] >= 10**9:
        raise PathfindError("no weighted path")
    path = [goal]
    while path[-1] != start:
        parent = prev.get(path[-1])
        if parent is None:
            raise PathfindError("broken path")
        path.append(parent)
    path.reverse()
    return {"path": path, "cost": dist[goal], "hops": len(path) - 1, "stored_prose": 0}


def extract_route(graph: Mapping[str, Any]) -> dict[str, Any]:
    nodes = list(graph.get("nodes") or [])
    spawn = next((node["id"] for node in nodes if node.get("kind") == "spawn"), None)
    extract = next((node["id"] for node in nodes if node.get("kind") == "extract"), None)
    if spawn is None or extract is None:
        raise PathfindError("spawn or extract missing")
    found = dijkstra(graph, str(spawn), str(extract))
    found["kind"] = "extract_route"
    found["warp_count"] = 1
    found["extract_count"] = 1
    return found
