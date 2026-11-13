"""Tile-level checks: does the tile map agree with the door graph?

The door graph is what lock placement and the solver reason about; the
tiles are what a player walks. These checks flood-fill the rendered tiles
with B044's gated navigation (``skeleton.frontier.worldsim.navigation``):
locked door tiles are gates, key tiles are pickups.

* :func:`tile_reach_without_keys` - rooms a player reaches holding nothing.
  Every one of them must also be reachable in the graph with all locks shut,
  otherwise a corridor bypasses a lock.
* :func:`tile_report` - the above, plus a full keyed run and softlock search
  on the tiles via ``detect_softlocks``.
"""
from __future__ import annotations

from skeleton.frontier.worldsim.navigation import GateSpec, NavGrid, detect_softlocks, gated_reachable

from .errors import ProcgenError
from .layout import Layout, bfs_depths


def _grid(layout: Layout) -> NavGrid:
    return NavGrid.from_rows(layout.tiles())


def _spec(layout: Layout, *, with_keys: bool) -> GateSpec:
    gates = {d.cell: d.key for d in layout.doors if d.key and d.cell is not None}
    keys = {c: k for k, c in layout.key_cells().items()} if with_keys else {}
    return GateSpec(gates=gates, keys=keys)  # type: ignore[arg-type]


def _rooms_of(layout: Layout, cells) -> set[str]:
    owner = layout.owner()
    return {owner[c] for c in cells if c in owner}


def tile_reach_without_keys(layout: Layout) -> set[str]:
    start = layout.room(layout.start).rect.center
    return _rooms_of(layout, gated_reachable(_grid(layout), _spec(layout, with_keys=False), start))


def graph_reach_without_keys(layout: Layout) -> set[str]:
    return set(bfs_depths(layout.adjacency(), layout.start, blocked=set(layout.locks())))


def tile_report(layout: Layout) -> dict:
    grid = _grid(layout)
    start = layout.room(layout.start).rect.center
    tile_free = tile_reach_without_keys(layout)
    graph_free = graph_reach_without_keys(layout)
    bypass = sorted(tile_free - graph_free)
    goal_cells = list(layout.room(layout.goal).rect.cells())
    keyed = _spec(layout, with_keys=True)
    soft = detect_softlocks(grid, keyed, start, goal_cells)
    reach_all = _rooms_of(layout, gated_reachable(grid, keyed, start))
    return {"ok": not bypass and soft["goal_reachable"] and not soft["softlock_cells"],
            "bypassed_locks_into": bypass, "goal_reachable": soft["goal_reachable"],
            "softlock_cells": len(soft["softlock_cells"]),
            "unreached_rooms": sorted({r.id for r in layout.rooms} - reach_all)}


def assert_tiles_match(layout: Layout) -> dict:
    rep = tile_report(layout)
    if rep["bypassed_locks_into"]:
        raise ProcgenError(f"tile route bypasses a lock into {rep['bypassed_locks_into']}")
    if not rep["goal_reachable"]:
        raise ProcgenError("goal not reachable on the tile map")
    return rep
