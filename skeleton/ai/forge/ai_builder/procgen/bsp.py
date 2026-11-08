"""Binary space partition room layouts.

The map is split recursively (iteratively, with an explicit stack) along the
longer axis until leaves are near ``min_leaf``; each leaf gets one room; the
two halves of every split are joined by an L corridor between their closest
rooms, which yields a spanning tree. ``loops`` adds extra corridors between
rooms in neighbouring leaves so the graph is not a pure tree.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.simulation.ecs.rng import DeterministicRng

from .errors import ProcgenError
from .layout import Layout, Rect, Room, carve_l, finalize


@dataclass(frozen=True)
class BspConfig:
    width: int = 64
    height: int = 48
    min_leaf: int = 10
    max_depth: int = 5
    room_margin: int = 1
    min_room: int = 4
    loops: float = 0.15

    def __post_init__(self) -> None:
        if not 16 <= self.width <= 256 or not 16 <= self.height <= 256:
            raise ProcgenError("bsp map must be 16..256 per side")
        if not 6 <= self.min_leaf <= min(self.width, self.height) // 2:
            raise ProcgenError("min_leaf must be >= 6 and at most half the map")
        if not 1 <= self.max_depth <= 10:
            raise ProcgenError("max_depth must be in [1, 10]")
        if not 3 <= self.min_room <= self.min_leaf - 2 * self.room_margin:
            raise ProcgenError("min_room must fit inside a leaf with margins")
        if not 0.0 <= self.loops <= 1.0:
            raise ProcgenError("loops must be in [0, 1]")


@dataclass
class _Node:
    rect: Rect
    depth: int
    left: "_Node | None" = None
    right: "_Node | None" = None
    room: Room | None = None


def _split(node: _Node, rng: DeterministicRng, cfg: BspConfig) -> bool:
    r = node.rect
    if node.depth >= cfg.max_depth:
        return False
    can_h = r.h >= 2 * cfg.min_leaf
    can_v = r.w >= 2 * cfg.min_leaf
    if not (can_h or can_v):
        return False
    if can_h and can_v:
        vertical = r.w > r.h * 1.25 or (not r.h > r.w * 1.25 and rng.chance(0.5))
    else:
        vertical = can_v
    if vertical:
        at = rng.randint(cfg.min_leaf, r.w - cfg.min_leaf)
        node.left = _Node(Rect(r.x, r.y, at, r.h), node.depth + 1)
        node.right = _Node(Rect(r.x + at, r.y, r.w - at, r.h), node.depth + 1)
    else:
        at = rng.randint(cfg.min_leaf, r.h - cfg.min_leaf)
        node.left = _Node(Rect(r.x, r.y, r.w, at), node.depth + 1)
        node.right = _Node(Rect(r.x, r.y + at, r.w, r.h - at), node.depth + 1)
    return True


def _rooms_under(node: _Node) -> list[Room]:
    out, stack = [], [node]
    while stack:
        n = stack.pop()
        if n.room:
            out.append(n.room)
        stack.extend(c for c in (n.right, n.left) if c)
    return out


def _closest(a: list[Room], b: list[Room]) -> tuple[Room, Room]:
    best = None
    for ra in a:
        ax, ay = ra.rect.center
        for rb in b:
            bx, by = rb.rect.center
            d = abs(ax - bx) + abs(ay - by)
            key = (d, ra.id, rb.id)
            if best is None or key < best[0]:
                best = (key, ra, rb)
    assert best is not None
    return best[1], best[2]


def bsp_layout(rng: DeterministicRng, cfg: BspConfig = BspConfig()) -> Layout:
    root = _Node(Rect(0, 0, cfg.width, cfg.height), 0)
    stack, leaves = [root], []
    while stack:
        n = stack.pop()
        if _split(n, rng, cfg):
            stack.append(n.right)  # type: ignore[arg-type]
            stack.append(n.left)   # type: ignore[arg-type]
        else:
            leaves.append(n)
    leaves.sort(key=lambda n: (n.rect.y, n.rect.x))
    m = cfg.room_margin
    for i, leaf in enumerate(leaves):
        r = leaf.rect
        max_w, max_h = r.w - 2 * m, r.h - 2 * m
        w = rng.randint(cfg.min_room, max_w)
        h = rng.randint(cfg.min_room, max_h)
        x = r.x + m + rng.randint(0, max_w - w)
        y = r.y + m + rng.randint(0, max_h - h)
        leaf.room = Room(f"r{i:02d}", Rect(x, y, w, h))
    links: list[tuple[str, str, tuple]] = []
    # join siblings bottom-up: post-order over internal nodes
    order, stack2 = [], [root]
    while stack2:
        n = stack2.pop()
        if n.left and n.right:
            order.append(n)
            stack2.extend((n.left, n.right))
    for n in reversed(order):
        a, b = _closest(_rooms_under(n.left), _rooms_under(n.right))  # type: ignore[arg-type]
        links.append((a.id, b.id, carve_l(a.rect.center, b.rect.center, rng.chance(0.5))))
    rooms = [leaf.room for leaf in leaves if leaf.room]
    for i in range(len(rooms) - 1):
        if rng.chance(cfg.loops):
            a, b = rooms[i], rooms[i + 1]
            links.append((a.id, b.id, carve_l(a.rect.center, b.rect.center, rng.chance(0.5))))
    return finalize(cfg.width, cfg.height, rooms, links, "bsp")
