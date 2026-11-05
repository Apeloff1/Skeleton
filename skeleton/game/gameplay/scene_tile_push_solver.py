"""Bounded deterministic shortest-action search for source-bound push puzzles.

Search never interprets exhaustion as an impossibility proof. Every successful
witness is replayed through the canonical push runtime before publication.
"""
from __future__ import annotations

import json
from collections import deque
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_push import (
    _step, export_push, legal_push_actions, new_push, resume_push, verify_push,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_tile_push_solver.v1"
MAX_STATES = 2048
MAX_DEPTH = 64


def _signature(session: dict[str, Any]) -> str:
    """Canonical action-relevant position for shortest-path dominance.

    This puzzle has no timed obstacles: reaching the same configuration
    earlier always leaves at least as many turns as a later arrival.
    Replay ticks, visited-history and save digests are *not* transition
    inputs. Keeping them in the search key made harmless loops consume
    the entire state budget before a valid solution could be reached.
    """
    state = session["state"]
    tile = state["tile"]["state"]
    scene = tile["scene"]["state"]
    return json.dumps({
        "scene_id": scene["scene_id"],
        "position": tile["position"],
        "inventory": scene["inventory"],
        "collected": scene["collected"],
        "crates": state["crates"],
        "phase": state["phase"],
    }, sort_keys=True, separators=(",", ":"))


def solve_push(source: Any, *, session: Any = None,
               target_phase: str = "won", max_states: int = 512,
               max_depth: int = 24) -> dict[str, Any]:
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid push solver state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid push solver depth budget")
    if type(target_phase) is not str or target_phase not in ("won", "lost", "draw"):
        raise SceneTravelError("invalid push target phase")
    start = verify_push(session) if session is not None else new_push(source)
    if session is not None and dig(start["source"]) != dig(
        new_push(source)["source"]
    ):
        raise SceneTravelError("push solver source/session mismatch")
    queue = deque([(start, [])])
    seen = {_signature(start)}
    explored, exhausted = 0, False
    while queue:
        current, actions = queue.popleft()
        explored += 1
        if current["state"]["phase"] == target_phase:
            final = resume_push(start, actions)
            if final["state_digest"] != current["state_digest"]:
                raise SceneTravelError("push solver witness replay mismatch")
            return {
                "schema_version": SCHEMA, "status": "found",
                "target_phase": target_phase,
                "source_digest": start["source_digest"],
                "initial_state_digest": start["state_digest"],
                "actions": actions, "explored": explored,
                "budget_exhausted": False,
                "max_states": max_states, "max_depth": max_depth,
                "final_state_digest": final["state_digest"],
                "portable_checksum": export_push(final)["checksum"],
            }
        if current["state"]["phase"] != "active":
            continue
        if len(actions) >= max_depth:
            exhausted = True
            continue
        for action in legal_push_actions(current):
            candidate = _step(current, action)
            key = _signature(candidate)
            if key in seen:
                continue
            if len(seen) >= max_states:
                exhausted = True
                break
            seen.add(key)
            queue.append((candidate, [*actions, action]))
        if len(seen) >= max_states:
            exhausted = True
            break
    return {
        "schema_version": SCHEMA,
        "status": "inconclusive" if exhausted else "unreachable",
        "target_phase": target_phase,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "actions": [], "explored": explored,
        "budget_exhausted": exhausted,
        "max_states": max_states, "max_depth": max_depth,
        "final_state_digest": None, "portable_checksum": None,
    }
