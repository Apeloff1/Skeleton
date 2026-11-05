"""Dungeon layout types shared by the BSP and graph generators.

A layout is rooms (axis-aligned rects on a tile grid), corridors (carved
cells) and doors (one per room-graph edge, optionally keyed). ``start`` and
``goal`` are room ids; ``critical_path`` is the room sequence from start to
goal that the lock placement and pacing work along.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping

from .canonical import digest
from .errors import ProcgenError

WALL, FLOOR, DOOR, LOCKED, START, GOAL, KEY, CORRIDOR = "#", ".", "+", "L", "S", "G", "k", ","


@dataclass(frozen=True, order=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def __post_init__(self) -> None:
        if min(self.w, self.h) < 1 or min(self.x, self.y) < 0:
            raise ProcgenError(f"bad rect {self}")

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2

    @property
    def area(self) -> int:
        return self.w * self.h

    def intersects(self, other: "Rect", pad: int = 0) -> bool:
        return not (self.x2 + pad <= other.x or other.x2 + pad <= self.x
                    or self.y2 + pad <= other.y or other.y2 + pad <= self.y)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x2 and self.y <= y < self.y2

    def cells(self) -> Iterable[tuple[int, int]]:
        for yy in range(self.y, self.y2):
            for xx in range(self.x, self.x2):
                yield xx, yy

    def as_list(self) -> list[int]:
        return [self.x, self.y, self.w, self.h]


@dataclass(frozen=True)
class Room:
    id: str
    rect: Rect
    depth: int = 0
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {"id": self.id, "rect": self.rect.as_list(), "depth": self.depth, "tags": list(self.tags)}


def edge(a: str, b: str) -> tuple[str, str]:
    if a == b:
        raise ProcgenError("self edge")
    return (a, b) if a < b else (b, a)


@dataclass(frozen=True)
class Door:
    a: str
    b: str
    key: str | None = None

    @property
    def edge(self) -> tuple[str, str]:
        return edge(self.a, self.b)

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "key": self.key}


@dataclass(frozen=True)
class Corridor:
    a: str
    b: str
    cells: tuple[tuple[int, int], ...]

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "length": len(self.cells)}


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    rooms: tuple[Room, ...]
    corridors: tuple[Corridor, ...]
    doors: tuple[Door, ...]
    start: str
    goal: str
    critical_path: tuple[str, ...]
    keys: Mapping[str, str] = field(default_factory=dict)   # key id -> room id holding it
    method: str = ""

    def __post_init__(self) -> None:
        ids = [r.id for r in self.rooms]
        if len(set(ids)) != len(ids):
            raise ProcgenError("duplicate room id")
        known = set(ids)
        for d in self.doors:
            if d.a not in known or d.b not in known:
                raise ProcgenError(f"door {d.a}-{d.b} references unknown room")
        if self.start not in known or self.goal not in known:
            raise ProcgenError("start/goal must be rooms")
        if set(self.critical_path) - known:
            raise ProcgenError("critical path references unknown room")
        door_keys = {d.key for d in self.doors if d.key}
        if door_keys - set(self.keys):
            raise ProcgenError(f"locked door with no key placed: {sorted(door_keys - set(self.keys))}")
        if set(self.keys.values()) - known:
            raise ProcgenError("key placed in unknown room")

    # -- graph ----------------------------------------------------------
    def room(self, rid: str) -> Room:
        for r in self.rooms:
            if r.id == rid:
                return r
        raise ProcgenError(f"unknown room {rid!r}")

    def adjacency(self) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {r.id: [] for r in self.rooms}
        for d in self.doors:
            adj[d.a].append(d.b)
            adj[d.b].append(d.a)
        return {k: sorted(set(v)) for k, v in adj.items()}

    def door(self, a: str, b: str) -> Door | None:
        e = edge(a, b)
        for d in self.doors:
            if d.edge == e:
                return d
        return None

    def locks(self) -> dict[tuple[str, str], str]:
        return {d.edge: d.key for d in self.doors if d.key}

    def depths(self) -> dict[str, int]:
        return bfs_depths(self.adjacency(), self.start)

    def with_doors(self, doors: Iterable[Door], keys: Mapping[str, str]) -> "Layout":
        return replace(self, doors=tuple(doors), keys=dict(keys))

    # -- export ---------------------------------------------------------
    def tiles(self) -> list[str]:
        grid = [[WALL] * self.width for _ in range(self.height)]
        for c in self.corridors:
            for x, y in c.cells:
                grid[y][x] = CORRIDOR
        for r in self.rooms:
            for x, y in r.rect.cells():
                grid[y][x] = FLOOR
        for d in self.doors:
            cor = next((c for c in self.corridors if edge(c.a, c.b) == d.edge), None)
            if cor and cor.cells:
                a = self.room(d.a).rect
                cell = next((p for p in cor.cells if not a.contains(*p)), cor.cells[0])
                grid[cell[1]][cell[0]] = LOCKED if d.key else DOOR
        for rid, mark in ((self.start, START), (self.goal, GOAL)):
            x, y = self.room(rid).rect.center
            grid[y][x] = mark
        for rid in self.keys.values():
            r = self.room(rid).rect
            x, y = r.center
            x = min(x + 1, r.x2 - 1)
            if grid[y][x] == FLOOR:
                grid[y][x] = KEY
        return ["".join(row) for row in grid]

    def as_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "method": self.method,
                "rooms": [r.as_dict() for r in self.rooms], "doors": [d.as_dict() for d in self.doors],
                "corridors": [c.as_dict() for c in self.corridors], "start": self.start, "goal": self.goal,
                "critical_path": list(self.critical_path), "keys": dict(sorted(self.keys.items()))}

    def digest(self) -> str:
        return digest({"layout": self.as_dict(), "tiles": self.tiles()})


# -- graph helpers ------------------------------------------------------

def bfs_depths(adj: Mapping[str, list[str]], start: str, *, blocked: set | None = None) -> dict[str, int]:
    blocked = blocked or set()
    seen = {start: 0}
    q = deque([start])
    while q:
        cur = q.popleft()
        for nxt in adj.get(cur, ()):
            if nxt not in seen and edge(cur, nxt) not in blocked:
                seen[nxt] = seen[cur] + 1
                q.append(nxt)
    return seen


def bfs_path(adj: Mapping[str, list[str]], start: str, goal: str) -> tuple[str, ...]:
    prev: dict[str, str | None] = {start: None}
    q = deque([start])
    while q:
        cur = q.popleft()
        if cur == goal:
            break
        for nxt in adj.get(cur, ()):
            if nxt not in prev:
                prev[nxt] = cur
                q.append(nxt)
    if goal not in prev:
        return ()
    path = [goal]
    while prev[path[-1]] is not None:
        path.append(prev[path[-1]])  # type: ignore[arg-type]
    return tuple(reversed(path))


def farthest(adj: Mapping[str, list[str]], start: str) -> str:
    d = bfs_depths(adj, start)
    return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def carve_l(a: tuple[int, int], b: tuple[int, int], horizontal_first: bool) -> tuple[tuple[int, int], ...]:
    """L-shaped corridor between two points, inclusive, no duplicate cells."""
    (x0, y0), (x1, y1) = a, b
    cells: list[tuple[int, int]] = []

    def run_x(y: int, xa: int, xb: int) -> None:
        step = 1 if xb >= xa else -1
        for x in range(xa, xb + step, step):
            cells.append((x, y))

    def run_y(x: int, ya: int, yb: int) -> None:
        step = 1 if yb >= ya else -1
        for y in range(ya, yb + step, step):
            cells.append((x, y))

    if horizontal_first:
        run_x(y0, x0, x1)
        run_y(x1, y0, y1)
    else:
        run_y(x0, y0, y1)
        run_x(y1, x0, x1)
    out, seen = [], set()
    for c in cells:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return tuple(out)


def finalize(width: int, height: int, rooms: list[Room], links: list[tuple[str, str, tuple]],
             method: str) -> Layout:
    """Pick start/goal by double BFS sweep (graph diameter) and set room depths."""
    if not rooms:
        raise ProcgenError("no rooms generated")
    adj: dict[str, list[str]] = {r.id: [] for r in rooms}
    seen_edges: set[tuple[str, str]] = set()
    corridors, doors = [], []
    for a, b, cells in links:
        e = edge(a, b)
        if e in seen_edges:
            continue
        seen_edges.add(e)
        adj[a].append(b)
        adj[b].append(a)
        corridors.append(Corridor(e[0], e[1], cells))
        doors.append(Door(e[0], e[1]))
    adj = {k: sorted(v) for k, v in adj.items()}
    first = rooms[0].id
    if len(bfs_depths(adj, first)) != len(rooms):
        raise ProcgenError("room graph is disconnected")
    start = farthest(adj, first)
    goal = farthest(adj, start) if len(rooms) > 1 else start
    path = bfs_path(adj, start, goal)
    depth = bfs_depths(adj, start)
    on_path = set(path)
    tagged = []
    for r in rooms:
        tags = []
        if r.id == start:
            tags.append("start")
        if r.id == goal:
            tags.append("goal")
        tags.append("critical" if r.id in on_path else "side")
        if len(adj[r.id]) == 1 and r.id not in (start, goal):
            tags.append("dead_end")
        tagged.append(replace(r, depth=depth[r.id], tags=tuple(tags)))
    return Layout(width, height, tuple(tagged), tuple(corridors), tuple(doors), start, goal, path, {}, method)
