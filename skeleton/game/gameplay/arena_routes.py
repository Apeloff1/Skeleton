"""Bounded deterministic tactical routing toward a reachable attack position.

A route is a movement plan only. Every move remains subject to the canonical
arena engine's occupancy and turn-order checks when actually executed.
"""
from __future__ import annotations
from collections import deque
from typing import Any

from skeleton.game.gameplay.turn_combat import CombatSessionError
from skeleton.game.gameplay.tactical_arena import (
    _active, legal_targets, verify_arena,
)

DIRECTIONS = (
    ("north", 0, -1), ("east", 1, 0),
    ("south", 0, 1), ("west", -1, 0),
)


def _route_verified(session: dict[str, Any]) -> list[str] | None:
    source, state = session["source"], session["state"]
    if state["phase"] != "active":
        raise CombatSessionError("cannot route terminal arena")
    actor_id, _ = _active(source, state)
    start = tuple(state["actors"][actor_id]["position"])
    blockers = {tuple(p) for p in source["walls"]}
    blockers.update(
        tuple(status["position"]) for key, status in state["actors"].items()
        if key != actor_id and status["hp"] > 0
    )
    width, height = source["width"], source["height"]
    queue = deque([(start, ())])
    visited = {start}
    # At most width*height distinct coordinates are ever enqueued.
    while queue:
        position, path = queue.popleft()
        hypothetical = {
            **state,
            "actors": {
                **state["actors"],
                actor_id: {**state["actors"][actor_id],
                           "position": list(position)},
            },
        }
        if legal_targets(source, hypothetical, actor_id):
            return list(path)
        x, y = position
        for direction, dx, dy in DIRECTIONS:
            nxt = (x + dx, y + dy)
            if (nxt in visited or nxt in blockers
                    or not 0 <= nxt[0] < width
                    or not 0 <= nxt[1] < height):
                continue
            visited.add(nxt)
            queue.append((nxt, (*path, direction)))
    return None


def route_to_attack(payload: Any) -> dict[str, Any]:
    """Verify the entire save before offering a source-bound tactical route."""
    session = verify_arena(payload)
    actor_id, _ = _active(session["source"], session["state"])
    route = _route_verified(session)
    return {
        "schema_version": "skeleton.arena_route.v1",
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "actor_id": actor_id,
        "reachable": route is not None,
        "moves": route,
    }
