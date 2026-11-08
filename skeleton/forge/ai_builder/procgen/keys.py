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
from dataclasses import dataclass, replace
from typing import Mapping

from skeleton.simulation.ecs.rng import DeterministicRng

from .errors import ProcgenError
from .layout import Layout, bfs_depths, edge


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


def place_locks(layout: Layout, rng: DeterministicRng, count: int, *, prefer_side: bool = True,
                max_key_distance: int | None = 4, strict: bool = False) -> Layout:
    """Put up to ``count`` locks on lockable, gating critical-path doors.

    Only doors whose tile cuts the only route between their rooms
    (``Door.lockable``) and whose removal separates start from goal are used,
    so every lock gates at least one room and none can be walked around. When
    fewer such doors exist than requested the shortfall is recorded in
    ``Layout.locks_requested`` (and raises with ``strict=True``). Each key sits
    at most ``max_key_distance`` door steps from the room in front of its lock
    when any candidate is that close; otherwise the closest candidate is used.
    """
    path = layout.critical_path
    requested = max(0, count)
    n_edges = max(len(path) - 1, 0)
    adj = layout.adjacency()
    lockable = {d.edge for d in layout.doors if d.lockable}
    gating = [i for i in range(n_edges)
              if edge(path[i], path[i + 1]) in lockable
              and layout.goal not in bfs_depths(adj, layout.start, blocked={edge(path[i], path[i + 1])})]
    count = min(requested, len(gating))
    if strict and count < requested:
        raise ProcgenError(f"asked for {requested} locks but only {len(gating)} lockable gating doors exist")
    if count == 0:
        return layout.with_doors(layout.doors, {}, locks_requested=requested)
    slots: list[int] = []
    for i in range(count):   # disjoint slices of the pool -> distinct slots, spread start..goal
        lo = (i * len(gating)) // count
        hi = ((i + 1) * len(gating)) // count - 1
        slots.append(gating[rng.randint(lo, hi)])
    lock_edges = [edge(path[s], path[s + 1]) for s in slots]
    critical = set(path)
    keys: dict[str, str] = {}
    lock_of: dict[tuple[str, str], str] = {}
    for i, (s_idx, e) in enumerate(zip(slots, lock_edges)):
        kid = f"key{i + 1}"
        blocked = set(lock_edges[i:])
        region = bfs_depths(adj, layout.start, blocked=blocked)
        near = bfs_depths(adj, path[s_idx], blocked=blocked)   # distance to the lock's front room
        used = set(keys.values())
        cands = [r for r in region if r != layout.goal]
        if max_key_distance is not None:
            close = [r for r in cands if near.get(r, 1 << 30) <= max_key_distance]
            if close:
                cands = close
            else:
                best = min(near.get(r, 1 << 30) for r in cands)
                cands = [r for r in cands if near.get(r, 1 << 30) == best]

        def score(rid: str) -> tuple:
            side = 0 if (prefer_side and rid not in critical) else 1
            return (side, rid in used, -region[rid], rid)

        ranked = sorted(cands, key=score)
        top = [r for r in ranked if score(r)[:2] == score(ranked[0])[:2]]
        weights = [1.0 + region[r] for r in top]
        keys[kid] = top[rng.weighted_index(weights)]
        lock_of[e] = kid
    doors = [replace(d, key=lock_of.get(d.edge)) for d in layout.doors]
    return layout.with_doors(doors, keys, locks_requested=requested)


def key_distances(adj: Mapping[str, list[str]], locks: Mapping[tuple[str, str], str],
                  keys: Mapping[str, str], start: str) -> dict[str, int | None]:
    """Door steps from each key's room to the nearer side of its lock (None if unreachable)."""
    out: dict[str, int | None] = {}
    for e, k in sorted(locks.items(), key=lambda kv: kv[1]):
        room = keys.get(k)
        if room is None:
            continue
        d = bfs_depths(adj, room)
        side = [d[x] for x in e if x in d]
        out[k] = min(side) if side else None
    return out


def solve(adj: Mapping[str, list[str]], start: str, goal: str, locks: Mapping[tuple[str, str], str],
          keys: Mapping[str, str]) -> Solution:
    """BFS over (room, keys held); keys are picked up on entering their room."""
    if (len(adj) > 4096 or len(locks) > 32 or len(keys) > 32 or start not in adj or goal not in adj):
        raise ProcgenError("lock solver exceeds finite graph admission budget")
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
                if len(prev) >= 65536:
                    raise ProcgenError("lock solver exhausted finite state budget")
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


def _key_order(k: str) -> tuple:
    digits = "".join(ch for ch in k if ch.isdigit())
    return (int(digits) if digits else 0, k)


def gates(adj: Mapping[str, list[str]], start: str, locks: Mapping[tuple[str, str], str]) -> dict[str, int]:
    """For each key, how many rooms its door(s) newly open once earlier keys are held.

    Works on directed adjacency. 0 means the lock gates nothing (it can be walked
    around, or sits behind a later lock). Keys are ordered by numeric suffix.
    """
    ranked = sorted(set(locks.values()), key=_key_order)
    out = {}
    for i, k in enumerate(ranked):
        later = {e for e, kk in locks.items() if kk in ranked[i + 1:]}
        mine = {e for e, kk in locks.items() if kk == k}
        with_it = bfs_depths(adj, start, blocked=later)
        without = bfs_depths(adj, start, blocked=later | mine)
        out[k] = len(with_it) - len(without)
    return out


def lock_gates(layout: Layout) -> dict[str, int]:
    return gates(layout.adjacency(), layout.start, layout.locks())


def softlocks(adj: Mapping[str, list[str]], start: str, goals, locks: Mapping[tuple[str, str], str],
              keys: Mapping[str, str]) -> dict:
    """Room-graph twin of B044 ``detect_softlocks``: reachable (room, keys) states with no way to a goal.

    ``adj`` is directed (one-way exits are honoured). A softlock is e.g. a
    one-way drop into a region whose only exit needs a key that is not there.
    """
    if len(adj) > 4096 or len(locks) > 32 or len(keys) > 32 or start not in adj:
        raise ProcgenError("softlock solver exceeds finite graph admission budget")
    key_at: dict[str, list[str]] = {}
    for k, r in keys.items():
        key_at.setdefault(r, []).append(k)

    def pick(room: str, held: frozenset) -> frozenset:
        got = key_at.get(room)
        return held | frozenset(got) if got else held

    def moves(state):
        room, held = state
        for nxt in adj.get(room, ()):
            need = locks.get(edge(room, nxt))
            if need and need not in held:
                continue
            yield (nxt, pick(nxt, held))

    goal_set = set(goals)
    s0 = (start, pick(start, frozenset()))
    states = {s0}
    q = deque([s0])
    succ: dict = {}
    while q:
        cur = q.popleft()
        succ[cur] = list(moves(cur))
        for ns in succ[cur]:
            if ns not in states:
                if len(states) >= 65536:
                    raise ProcgenError("softlock solver exhausted finite state budget")
                states.add(ns)
                q.append(ns)
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
    bad = sorted({s[0] for s in states if s not in good})
    return {"ok": not bad and bool(good), "goal_reachable": bool(good), "softlock_rooms": bad}


def assert_solvable(layout: Layout) -> Solution:
    sol = solve_layout(layout)
    if not sol.solvable:
        raise ProcgenError(f"layout not solvable; stuck on {list(sol.stuck_on)}")
    return sol
