"""Graph-based room layouts: scatter rooms, minimum spanning tree, extra loops.

Rooms are placed by rejection sampling (no overlaps, ``spacing`` cells
apart). Corridors follow a Prim MST over room-centre Manhattan distance; then
each non-tree edge among each room's ``k`` nearest neighbours is added with
probability ``loops``.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.simulation.ecs.rng import DeterministicRng

from .errors import ProcgenError
from .layout import Layout, Rect, Room, carve_l, edge, finalize


@dataclass(frozen=True)
class GraphConfig:
    width: int = 64
    height: int = 48
    rooms: int = 10
    min_size: int = 4
    max_size: int = 9
    spacing: int = 2
    attempts: int = 400
    loops: float = 0.2
    k_nearest: int = 3

    def __post_init__(self) -> None:
        if not 16 <= self.width <= 256 or not 16 <= self.height <= 256:
            raise ProcgenError("graph map must be 16..256 per side")
        if not 2 <= self.rooms <= 64:
            raise ProcgenError("rooms must be in [2, 64]")
        if not 3 <= self.min_size <= self.max_size <= min(self.width, self.height) // 2:
            raise ProcgenError("need 3 <= min_size <= max_size <= half the map")
        if not 0 <= self.spacing <= 8 or not 10 <= self.attempts <= 20_000:
            raise ProcgenError("spacing in [0, 8], attempts in [10, 20000]")
        if not 0.0 <= self.loops <= 1.0 or not 1 <= self.k_nearest <= 8:
            raise ProcgenError("loops in [0, 1], k_nearest in [1, 8]")


def _dist(a: Room, b: Room) -> int:
    (ax, ay), (bx, by) = a.rect.center, b.rect.center
    return abs(ax - bx) + abs(ay - by)


def scatter(rng: DeterministicRng, cfg: GraphConfig) -> list[Room]:
    placed: list[Rect] = []
    for _ in range(cfg.attempts):
        if len(placed) >= cfg.rooms:
            break
        w = rng.randint(cfg.min_size, cfg.max_size)
        h = rng.randint(cfg.min_size, cfg.max_size)
        x = rng.randint(1, cfg.width - w - 1)
        y = rng.randint(1, cfg.height - h - 1)
        r = Rect(x, y, w, h)
        if any(r.intersects(p, cfg.spacing) for p in placed):
            continue
        placed.append(r)
    if len(placed) < 2:
        raise ProcgenError("could not place at least two rooms; enlarge the map or lower sizes")
    placed.sort(key=lambda r: (r.y, r.x))
    return [Room(f"r{i:02d}", r) for i, r in enumerate(placed)]


def mst(rooms: list[Room]) -> list[tuple[Room, Room]]:
    """Prim's algorithm, ties broken by id so the tree is unique."""
    inside = {rooms[0].id}
    by_id = {r.id: r for r in rooms}
    out = []
    while len(inside) < len(rooms):
        best = None
        for a in sorted(inside):
            ra = by_id[a]
            for rb in rooms:
                if rb.id in inside:
                    continue
                key = (_dist(ra, rb), ra.id, rb.id)
                if best is None or key < best[0]:
                    best = (key, ra, rb)
        assert best is not None
        out.append((best[1], best[2]))
        inside.add(best[2].id)
    return out


def graph_layout(rng: DeterministicRng, cfg: GraphConfig = GraphConfig()) -> Layout:
    rooms = scatter(rng, cfg)
    tree = mst(rooms)
    links: list[tuple[str, str, tuple]] = []
    used = set()
    for a, b in tree:
        used.add(edge(a.id, b.id))
        links.append((a.id, b.id, carve_l(a.rect.center, b.rect.center, rng.chance(0.5))))
    for a in rooms:
        near = sorted((r for r in rooms if r.id != a.id), key=lambda r: (_dist(a, r), r.id))[:cfg.k_nearest]
        for b in near:
            e = edge(a.id, b.id)
            if e in used:
                continue
            if rng.chance(cfg.loops):
                used.add(e)
                links.append((a.id, b.id, carve_l(a.rect.center, b.rect.center, rng.chance(0.5))))
    return finalize(cfg.width, cfg.height, rooms, links, "graph")
