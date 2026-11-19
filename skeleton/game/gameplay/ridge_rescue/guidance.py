"""Bounded static route guidance. Dynamic enemies can invalidate a route; never certify victory."""
from __future__ import annotations
from collections import deque
from .schema import World
from .engine import DIRECTIONS

def route(world: World, start: tuple[int, int], goal: tuple[int, int], blocked: frozenset[tuple[int, int]] = frozenset()) -> list[str] | None:
    if not world.walkable(start) or not world.walkable(goal):
        return None
    queue = deque([start])
    parents: dict[tuple[int, int], tuple[tuple[int, int], str] | None] = {start: None}
    while queue:
        point = queue.popleft()
        if point == goal:
            steps: list[str] = []
            while parents[point] is not None:
                parent, direction = parents[point]
                steps.append(direction)
                point = parent
            return list(reversed(steps))
        for direction, (dx, dy) in sorted(DIRECTIONS.items()):
            next_point = (point[0] + dx, point[1] + dy)
            if next_point in parents or next_point in blocked or not world.walkable(next_point) or world.tile(next_point) == "~":
                continue
            parents[next_point] = (point, direction)
            queue.append(next_point)
    return None

def hint(world: World, state: dict) -> dict:
    here = tuple(state["position"])
    if state["status"] != "playing":
        return {"kind": "finished", "status": state["status"], "guaranteed": False}
    obstacles = frozenset(tuple(v["at"]) for v in state["raiders"].values() if v["health"] > 0)
    waiting = [(ident, at) for ident, at in world.civilians if state["civilians"][ident] == "waiting"]
    candidates: list[tuple[int, str, str, list[str]]] = []
    for ident, target in waiting:
        for dx, dy in DIRECTIONS.values():
            neighbor = (target[0] + dx, target[1] + dy)
            path = route(world, here, neighbor, obstacles)
            if path is not None:
                candidates.append((len(path), "rescue", ident, path))
    if not waiting:
        path = route(world, here, world.shelter, obstacles)
        if path is not None:
            candidates.append((len(path), "shelter", "shelter", path))
    for ident, kind, at, count in world.resources:
        if state["resources"][ident] == 0:
            continue
        for dx, dy in DIRECTIONS.values():
            neighbor = (at[0] + dx, at[1] + dy)
            path = route(world, here, neighbor, obstacles)
            if path is not None:
                candidates.append((len(path) + 2, "gather", ident, path))
    if not candidates:
        return {"kind": "blocked", "guaranteed": False, "reason": "no static path"}
    distance, kind, target, steps = min(candidates)
    return {"kind": kind, "target": target, "directions": steps, "distance": distance, "guaranteed": False}
