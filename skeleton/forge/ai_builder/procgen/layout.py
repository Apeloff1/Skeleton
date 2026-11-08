"""Dungeon layout types shared by the BSP and graph generators.

A layout is rooms (axis-aligned rects on a tile grid), corridors (carved
cells) and doors (one per room-graph edge, optionally keyed). ``start`` and
``goal`` are room ids; ``critical_path`` is the room sequence from start to
goal that the lock placement and pacing work along.
"""
from __future__ import annotations

from collections import deque
from itertools import combinations
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
    """A room-graph edge as it exists on the tile map.

    ``cell`` is the single corridor tile that cuts every tile route between
    ``a`` and ``b`` (None when no such tile exists, e.g. rooms that touch or
    a corridor junction shared by three rooms). Only ``lockable`` doors may
    carry a key: locking anything else could be walked around on the tiles.
    """
    a: str
    b: str
    key: str | None = None
    cell: tuple[int, int] | None = None
    lockable: bool = False

    @property
    def edge(self) -> tuple[str, str]:
        return edge(self.a, self.b)

    def as_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "key": self.key,
                "cell": None if self.cell is None else list(self.cell), "lockable": self.lockable}


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
    locks_requested: int = 0

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
        bad = sorted(f"{d.a}-{d.b}" for d in self.doors if d.key and not d.lockable)
        if bad:
            raise ProcgenError(f"lock on a door the tiles can bypass: {bad}")

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

    def with_doors(self, doors: Iterable[Door], keys: Mapping[str, str], *,
                   locks_requested: int | None = None) -> "Layout":
        extra = {} if locks_requested is None else {"locks_requested": locks_requested}
        return replace(self, doors=tuple(doors), keys=dict(keys), **extra)

    def key_cell(self, rid: str) -> tuple[int, int]:
        """Tile where the key for a room is drawn (next to the centre, never on it)."""
        r = self.room(rid).rect
        x, y = r.center
        return min(x + 1, r.x2 - 1) if r.w > 1 else x, y

    def key_cells(self) -> dict[str, tuple[int, int]]:
        """One distinct tile per key; several keys in one room get neighbouring tiles."""
        out: dict[str, tuple[int, int]] = {}
        taken: set[tuple[int, int]] = set()
        for k, rid in sorted(self.keys.items()):
            r = self.room(rid).rect
            first = self.key_cell(rid)
            order = [first] + sorted((c for c in r.cells() if c != r.center and c != first),
                                     key=lambda c: (abs(c[0] - first[0]) + abs(c[1] - first[1]), c))
            cell = next(c for c in order if c not in taken and c != r.center)
            taken.add(cell)
            out[k] = cell
        return out

    def owner(self) -> dict[tuple[int, int], str]:
        return {c: r.id for r in self.rooms for c in r.rect.cells()}

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
            if d.cell is not None:
                grid[d.cell[1]][d.cell[0]] = LOCKED if d.key else DOOR
        for rid, mark in ((self.start, START), (self.goal, GOAL)):
            x, y = self.room(rid).rect.center
            grid[y][x] = mark
        for x, y in self.key_cells().values():
            if grid[y][x] == FLOOR:
                grid[y][x] = KEY
        return ["".join(row) for row in grid]

    def as_dict(self) -> dict:
        return {"width": self.width, "height": self.height, "method": self.method,
                "rooms": [r.as_dict() for r in self.rooms], "doors": [d.as_dict() for d in self.doors],
                "corridors": [c.as_dict() for c in self.corridors], "start": self.start, "goal": self.goal,
                "critical_path": list(self.critical_path), "keys": dict(sorted(self.keys.items())),
                "locks_requested": self.locks_requested}

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


def _nbrs(c: tuple[int, int]):
    x, y = c
    return ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))


def _cut_cell(comp: list[tuple[int, int]], a: str, b: str, owner: Mapping[tuple[int, int], str],
              near_a: Rect) -> tuple[int, int] | None:
    """A component tile whose removal disconnects room ``a`` from room ``b`` (prefers tiles next to ``a``)."""
    cells = set(comp)
    side_a = {c for c in comp if any(owner.get(n) == a for n in _nbrs(c))}
    side_b = {c for c in comp if any(owner.get(n) == b for n in _nbrs(c))}

    def connected_without(cut: tuple[int, int]) -> bool:
        seeds = [c for c in side_a if c != cut]
        seen, stack = set(seeds), list(seeds)
        while stack:
            cur = stack.pop()
            if cur in side_b:
                return True
            for n in _nbrs(cur):
                if n in cells and n != cut and n not in seen:
                    seen.add(n)
                    stack.append(n)
        return False

    def dist(c: tuple[int, int]) -> int:
        x, y = c
        dx = max(near_a.x - x, 0, x - (near_a.x2 - 1))
        dy = max(near_a.y - y, 0, y - (near_a.y2 - 1))
        return dx + dy

    for cand in sorted(comp, key=lambda c: (dist(c), c)):
        if not connected_without(cand):
            return cand
    return None


def tile_links(rooms: list[Room], links: list[tuple[str, str, tuple]]
               ) -> list[tuple[str, str, tuple, tuple[int, int] | None]]:
    """Room connections as the carved tiles actually make them.

    An L corridor may cross a third room or another corridor; each 4-connected
    component of carved non-room cells therefore links *every* room it touches
    (a corridor through room X yields a-X and X-b). Rooms that touch each other
    link directly. Returns ``(a, b, cells, door_cell)``; ``door_cell`` is set
    only when one tile cuts the only route between exactly two rooms.
    """
    owner = {c: r.id for r in rooms for c in r.rect.cells()}
    rect = {r.id: r.rect for r in rooms}
    carved = {c for _, _, cells in links for c in cells if c not in owner}
    out: dict[tuple[str, str], list] = {}
    seen: set[tuple[int, int]] = set()
    for c0 in sorted(carved):
        if c0 in seen:
            continue
        comp, stack = [], [c0]
        seen.add(c0)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for n in _nbrs(cur):
                if n in carved and n not in seen:
                    seen.add(n)
                    stack.append(n)
        comp.sort()
        touch = sorted({owner[n] for c in comp for n in _nbrs(c) if n in owner})
        cut = None
        if len(touch) == 2:
            cut = _cut_cell(comp, touch[0], touch[1], owner, rect[touch[0]])
        for a, b in combinations(touch, 2):
            e = edge(a, b)
            if e in out:   # a second route between the same rooms: no single tile can lock it
                out[e] = [e[0], e[1], tuple(sorted(set(out[e][2]) | set(comp))), None]
            else:
                out[e] = [e[0], e[1], tuple(comp), cut]
    for c, rid in sorted(owner.items()):
        for n in _nbrs(c):
            other = owner.get(n)
            if other is not None and other != rid:
                e = edge(rid, other)
                if e in out:
                    out[e][3] = None
                else:
                    out[e] = [e[0], e[1], (), None]
    return [tuple(v) for _, v in sorted(out.items())]  # type: ignore[misc]


def finalize(width: int, height: int, rooms: list[Room], links: list[tuple[str, str, tuple]],
             method: str) -> Layout:
    """Derive the door graph from the carved tiles, pick start/goal by double BFS, set depths."""
    if not rooms:
        raise ProcgenError("no rooms generated")
    adj: dict[str, list[str]] = {r.id: [] for r in rooms}
    corridors, doors = [], []
    for a, b, cells, cut in tile_links(rooms, links):
        adj[a].append(b)
        adj[b].append(a)
        corridors.append(Corridor(a, b, cells))
        doors.append(Door(a, b, None, cut, cut is not None))
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
