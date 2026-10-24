"""B044 navigation generation: grid nav surfaces, A*, dynamic obstacles, reachability."""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Iterable, Sequence

Cell = tuple[int, int]


class NavError(ValueError):
    pass


@dataclass
class NavGrid:
    width: int
    height: int
    blocked: set[Cell] = field(default_factory=set)
    dynamic: set[Cell] = field(default_factory=set)

    @classmethod
    def from_rows(cls, rows: Sequence[str]) -> "NavGrid":
        if not rows or len({len(r) for r in rows}) != 1:
            raise NavError("rows must be non-empty and rectangular")
        blocked = {(x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == "#"}
        return cls(len(rows[0]), len(rows), blocked)

    def walkable(self, c: Cell) -> bool:
        x, y = c
        return 0 <= x < self.width and 0 <= y < self.height and c not in self.blocked and c not in self.dynamic

    def neighbors(self, c: Cell) -> Iterable[Cell]:
        x, y = c
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self.walkable(n):
                yield n

    def set_obstacles(self, cells: Iterable[Cell]) -> None:
        self.dynamic = set(cells)


def find_path(grid: NavGrid, start: Cell, goal: Cell) -> list[Cell] | None:
    if not grid.walkable(start) or not grid.walkable(goal):
        return None
    h = lambda c: abs(c[0] - goal[0]) + abs(c[1] - goal[1])  # noqa: E731
    open_: list[tuple[int, int, Cell]] = [(h(start), 0, start)]
    came: dict[Cell, Cell] = {}
    g = {start: 0}
    while open_:
        _, cost, cur = heapq.heappop(open_)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return path[::-1]
        if cost > g[cur]:
            continue
        for n in sorted(grid.neighbors(cur)):
            nc = cost + 1
            if nc < g.get(n, 1 << 30):
                g[n], came[n] = nc, cur
                heapq.heappush(open_, (nc + h(n), nc, n))
    return None


def reachable_from(grid: NavGrid, start: Cell) -> set[Cell]:
    if not grid.walkable(start):
        return set()
    seen, stack = {start}, [start]
    while stack:
        for n in grid.neighbors(stack.pop()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    return seen


def reachability_report(grid: NavGrid, start: Cell, required: Iterable[Cell]) -> dict:
    reach = reachable_from(grid, start)
    req = sorted(set(required))
    missing = [c for c in req if c not in reach]
    open_cells = grid.width * grid.height - len(grid.blocked | grid.dynamic)
    return {"ok": not missing, "unreachable": missing,
            "coverage": round(len(reach) / open_cells, 6) if open_cells else 0.0}


# --- Gated reachability and softlock detection (Wally review on #4268) ---

Edge = tuple[Cell, Cell]


@dataclass(frozen=True)
class GateSpec:
    """Gates block a cell until ``key`` is held; keys are picked up on entry.

    ``one_way`` edges (a, b) allow moving a -> b only (b -> a is removed).
    """
    gates: dict[Cell, str] = field(default_factory=dict)
    keys: dict[Cell, str] = field(default_factory=dict)
    one_way: frozenset[Edge] = frozenset()


def _gated_neighbors(grid: NavGrid, spec: GateSpec, c: Cell, held: frozenset[str]):
    for n in grid.neighbors(c):
        if (n, c) in spec.one_way and (c, n) not in spec.one_way:
            continue
        need = spec.gates.get(n)
        if need is not None and need not in held:
            continue
        yield n


def gated_states(grid: NavGrid, spec: GateSpec, start: Cell) -> dict[tuple[Cell, frozenset[str]], tuple]:
    """BFS over (cell, keys held). Returns state -> predecessor state."""
    if not grid.walkable(start):
        return {}
    s0 = (start, frozenset({spec.keys[start]}) if start in spec.keys else frozenset())
    prev: dict = {s0: None}
    queue = [s0]
    while queue:
        cell, held = state = queue.pop(0)
        for n in sorted(_gated_neighbors(grid, spec, cell, held)):
            nh = held | {spec.keys[n]} if n in spec.keys else held
            ns = (n, frozenset(nh))
            if ns not in prev:
                prev[ns] = state
                queue.append(ns)
    return prev


def gated_reachable(grid: NavGrid, spec: GateSpec, start: Cell) -> set[Cell]:
    return {cell for cell, _ in gated_states(grid, spec, start)}


def detect_softlocks(grid: NavGrid, spec: GateSpec, start: Cell, goals: Iterable[Cell]) -> dict:
    """Find reachable states from which no goal is reachable any more.

    A softlock is a (cell, keys) state reachable from ``start`` whose own
    forward closure contains no goal cell (e.g. past a one-way drop without
    the key for the exit gate).
    """
    goal_set = set(goals)
    states = gated_states(grid, spec, start)
    # reverse graph over discovered states, then backward-search from goal states
    succ: dict = {s: [] for s in states}
    for s, p in states.items():
        if p is not None:
            succ[p].append(s)
    for (cell, held) in states:
        for n in _gated_neighbors(grid, spec, cell, held):
            nh = held | {spec.keys[n]} if n in spec.keys else held
            ns = (n, frozenset(nh))
            if ns in states and ns not in succ[(cell, held)]:
                succ[(cell, held)].append(ns)
    pred: dict = {s: [] for s in states}
    for s, outs in succ.items():
        for t in outs:
            pred[t].append(s)
    good = {s for s in states if s[0] in goal_set}
    stack = list(good)
    while stack:
        for p in pred[stack.pop()]:
            if p not in good:
                good.add(p)
                stack.append(p)
    locked = sorted({s[0] for s in states if s not in good})
    return {"ok": not locked and bool(good), "goal_reachable": bool(good),
            "softlock_cells": locked}
