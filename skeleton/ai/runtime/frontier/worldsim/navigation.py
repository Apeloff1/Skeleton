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
