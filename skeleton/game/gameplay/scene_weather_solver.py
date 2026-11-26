"""Bounded, deterministic, replay-proven route planning for weather-gated scenes.

This planner never shortcuts canonical traversal, weather collision or inventory
checks. A budget-exhausted search is inconclusive, not proof of unreachability.
"""
from __future__ import annotations

from collections import deque
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _limit
from skeleton.game.gameplay.scene_weather import (
    _advance, new_session, resume_session, verify_session,
)

MAX_STATES = 512
MAX_DEPTH = 64


def _actions(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Stable original-source order: collect, travel, then wait."""
    scene_id = snapshot["state"]["scene"]["state"]["scene_id"]
    source = snapshot["source"]["world"]
    scene = next(entry for entry in source["scenes"] if entry["id"] == scene_id)
    collected = set(snapshot["state"]["scene"]["state"]["collected"])
    actions: list[dict[str, Any]] = []
    for pickup in scene["pickups"]:
        if f'{scene_id}:{pickup["id"]}' not in collected:
            actions.append({"kind": "scene", "action": {
                "kind": "collect", "pickup_id": pickup["id"],
            }})
    for edge in scene["exits"]:
        actions.append({"kind": "scene", "action": {
            "kind": "travel", "exit_id": edge["id"],
        }})
    actions.append({"kind": "wait"})
    return actions


def _report(
    status: str, start: dict[str, Any], explored: int,
    *, actions: list[dict[str, Any]] | None = None,
    terminal: dict[str, Any] | None = None,
    complete: bool = False,
) -> dict[str, Any]:
    return {
        "schema_version": "skeleton.scene_weather_route.v1",
        "status": status, "complete": complete, "explored": explored,
        "source_digest": start["source_digest"],
        "start_state_digest": start["state_digest"],
        "actions": [] if actions is None else actions,
        "terminal_state_digest": (
            None if terminal is None else terminal["state_digest"]
        ),
        "terminal_session": terminal,
    }


def plan_weather(
    source: Any = None, *, session: Any = None,
    max_states: int = 256, max_depth: int = 32,
) -> dict[str, Any]:
    """Return shortest legal victory witness, or a fail-closed search status.

    The returned terminal session is independently replay-verifiable. A
    resumed route is bound to the complete original source and save lineage.
    """
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one weather source or checkpoint")
    _limit(max_states, "max_states", 1, MAX_STATES)
    _limit(max_depth, "max_depth", 0, MAX_DEPTH)
    start = new_session(source) if session is None else verify_session(session)
    phase = start["state"]["phase"]
    if phase == "won":
        return _report("solved", start, 1, actions=[], terminal=start, complete=True)
    if phase != "active":
        return _report("unreachable", start, 1, complete=True)

    frontier = deque([(start, [])])
    seen = {dig(start["state"])}
    explored = 0
    truncated = False
    while frontier:
        node, path = frontier.popleft()
        explored += 1
        if len(path) >= max_depth:
            truncated = True
            continue
        for action in _actions(node):
            try:
                successor = _advance(node, action)
            except SceneTravelError:
                # Illegal exit or unearned item; canonical state remains intact.
                continue
            witness = [*path, action]
            if successor["state"]["phase"] == "won":
                replayed = resume_session(start, witness)
                if replayed != successor or verify_session(replayed) != successor:
                    raise SceneTravelError("weather route witness replay mismatch")
                return _report(
                    "solved", start, explored, actions=witness,
                    terminal=replayed, complete=True,
                )
            if successor["state"]["phase"] != "active":
                continue
            identity = dig(successor["state"])
            if identity in seen:
                continue
            if len(seen) >= max_states:
                truncated = True
                continue
            seen.add(identity)
            frontier.append((successor, witness))
    return _report(
        "inconclusive" if truncated else "unreachable",
        start, explored, complete=not truncated,
    )
