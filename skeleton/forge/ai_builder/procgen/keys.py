"""Keyed doors along the critical path, and a lock-and-key solver.

Locks go on critical-path edges, spread evenly from start to goal. The key
for lock *i* is placed in a room reachable from the start when locks
``i..n`` are closed (keys ``0..i-1`` already usable), preferring side rooms
over critical-path rooms and deeper rooms over shallow ones. Construction
therefore always yields a solvable layout; :func:`solve` re-checks it
independently by BFS over ``(room, keys held)``.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Mapping

from skeleton.simulation.ecs.rng import DeterministicRng

from .errors import ProcgenError
from .layout import Door, Layout, bfs_depths, edge


@dataclass(frozen=True)
class Solution:
    solvable: bool
    order: tuple[str, ...]          # keys in pickup order
    steps: int                      # room moves on the found route
    reachable: frozenset[str]       # rooms reachable at all
    unreachable: tuple[str, ...]
    stuck_on: tuple[str, ...]       # keys that were needed but never found

    def as_dict(self) -> dict:
        return {"solvable": self.solvable, "order": list(self.order), "steps": self.steps,
                "unreachable": list(self.unreachable), "stuck_on": list(self.stuck_on)}


def place_locks(layout: Layout, rng: DeterministicRng, count: int, *, prefer_side: bool = True) -> Layout:
    path = layout.critical_path
    count = max(0, min(count, len(path) - 1))
    if count == 0:
        return layout.with_doors(layout.doors, {})
    n_edges = len(path) - 1
    adj = layout.adjacency()
    # path edges whose removal cuts start from goal really gate progress; prefer them
    gating = [i for i in range(n_edges)
              if layout.goal not in bfs_depths(adj, layout.start, blocked={edge(path[i], path[i + 1])})]
    pool = gating if len(gating) >= count else list(range(n_edges))
    slots: list[int] = []
    for i in range(count):
        lo = (i * len(pool)) // count
        hi = max(lo, ((i + 1) * len(pool)) // count - 1)
        slots.append(pool[rng.randint(lo, hi)])
    slots = sorted(set(slots))
    lock_edges = [edge(path[s], path[s + 1]) for s in slots]
    critical = set(path)
    keys: dict[str, str] = {}
    lock_of: dict[tuple[str, str], str] = {}
    for i, e in enumerate(lock_edges):
        kid = f"key{i + 1}"
        blocked = set(lock_edges[i:])
        region = bfs_depths(adj, layout.start, blocked=blocked)
        used = set(keys.values())
        cands = [r for r in region if r != layout.goal]

        def score(rid: str) -> tuple:
            side = 0 if (prefer_side and rid not in critical) else 1
            return (side, rid in used, -region[rid], rid)

        ranked = sorted(cands, key=score)
        top = [r for r in ranked if score(r)[:2] == score(ranked[0])[:2]]
        # jitter among the best tier, weighted toward depth
        weights = [1.0 + region[r] for r in top]
        keys[kid] = top[rng.weighted_index(weights)]
        lock_of[e] = kid
    doors = [Door(d.a, d.b, lock_of.get(d.edge)) for d in layout.doors]
    return layout.with_doors(doors, keys)


def solve(adj: Mapping[str, list[str]], start: str, goal: str, locks: Mapping[tuple[str, str], str],
          keys: Mapping[str, str]) -> Solution:
    """BFS over (room, keys held); keys are picked up on entering their room."""
    key_at: dict[str, list[str]] = {}
    for k, r in keys.items():
        key_at.setdefault(r, []).append(k)

    def pick(room: str, held: frozenset) -> frozenset:
        got = key_at.get(room)
        return held | frozenset(got) if got else held

    s0 = (start, pick(start, frozenset()))
    prev: dict[tuple, tuple | None] = {s0: None}
    q = deque([s0])
    found = None
    reach = {start}
    while q:
        cur = q.popleft()
        room, held = cur
        reach.add(room)
        if room == goal and found is None:
            found = cur
        for nxt in adj.get(room, ()):
            need = locks.get(edge(room, nxt))
            if need and need not in held:
                continue
            st = (nxt, pick(nxt, held))
            if st not in prev:
                prev[st] = cur
                q.append(st)
    all_rooms = set(adj)
    unreachable = tuple(sorted(all_rooms - reach))
    held_ever = frozenset().union(*(h for _, h in prev))
    stuck = tuple(sorted(set(locks.values()) - held_ever))
    if found is None:
        return Solution(False, (), 0, frozenset(reach), unreachable, stuck)
    chain = []
    node: tuple | None = found
    while node is not None:
        chain.append(node)
        node = prev[node]
    chain.reverse()
    order: list[str] = []
    for _, held in chain:
        for k in sorted(held):
            if k not in order:
                order.append(k)
    return Solution(True, tuple(order), len(chain) - 1, frozenset(reach), unreachable, stuck)


def solve_layout(layout: Layout) -> Solution:
    return solve(layout.adjacency(), layout.start, layout.goal, layout.locks(), layout.keys)


def lock_gates(layout: Layout) -> dict[str, int]:
    """For each key, how many rooms its door newly opens once earlier keys are held.

    0 means the lock can be walked around. Keys are ordered by their numeric suffix.
    """
    adj = layout.adjacency()
    locks = layout.locks()

    def order(k: str) -> tuple:
        digits = "".join(ch for ch in k if ch.isdigit())
        return (int(digits) if digits else 0, k)

    ranked = sorted(set(locks.values()), key=order)
    out = {}
    for i, k in enumerate(ranked):
        later = {e for e, kk in locks.items() if kk in ranked[i + 1:]}
        mine = {e for e, kk in locks.items() if kk == k}
        with_it = bfs_depths(adj, layout.start, blocked=later)
        without = bfs_depths(adj, layout.start, blocked=later | mine)
        out[k] = len(with_it) - len(without)
    return out


def assert_solvable(layout: Layout) -> Solution:
    sol = solve_layout(layout)
    if not sol.solvable:
        raise ProcgenError(f"layout not solvable; stuck on {list(sol.stuck_on)}")
    return sol
