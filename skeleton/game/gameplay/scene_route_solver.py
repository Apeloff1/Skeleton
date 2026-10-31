"""Bounded, deterministic victory routing over real canonical scene transitions.

This solver explores legal actions using the authoritative scene engine.
It never fabricates a winning path: every returned route has been executed
through canonical _advance and is bound to exact authored source identity.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance, _json, _scene, new_session, original_demo,
    verify_session,
)

SOLVER_SCHEMA = "skeleton.scene_route.v1"
MAX_SEARCH_STATES = 4096
MAX_SEARCH_DEPTH = 512


def _state_key(state: dict[str, Any]) -> tuple[Any, ...]:
    # Visited scene display order does not affect future legal actions.
    return (
        state["scene_id"], tuple(state["inventory"]),
        tuple(state["collected"]),
    )


def _options(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    state = snapshot["state"]
    scene = _scene(snapshot["world"], state["scene_id"])
    actions: list[dict[str, str]] = []
    for pickup in scene["pickups"]:
        if scene["id"] + ":" + pickup["id"] not in state["collected"]:
            actions.append({"kind": "collect", "pickup_id": pickup["id"]})
    for edge in scene["exits"]:
        required = edge["requires_item"]
        if required is None or required in state["inventory"]:
            actions.append({"kind": "travel", "exit_id": edge["id"]})
    return sorted(
        actions,
        key=lambda item: (
            item["kind"], item.get("pickup_id", item.get("exit_id", "")),
        ),
    )


def plan_victory(
    world: Any = None, *,
    session: Any = None,
    max_states: int = 1024,
    max_depth: int = 64,
) -> dict[str, Any]:
    """Find a shortest replayable route, or explicitly refuse to overclaim.

    An exhausted full bounded search is unreachable. A state/depth budget
    truncation is inconclusive, never a claim that a game cannot be won.
    """
    if (world is None) == (session is None):
        raise SceneTravelError("supply exactly one world or saved session")
    if type(max_states) is not int or not 1 <= max_states <= MAX_SEARCH_STATES:
        raise SceneTravelError("invalid search state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_SEARCH_DEPTH:
        raise SceneTravelError("invalid search depth budget")
    start = new_session(world) if session is None else verify_session(session)
    source = start["source_digest"]
    initial = start["state_digest"]
    if start["state"]["phase"] == "won":
        return {
            "schema_version": SOLVER_SCHEMA, "status": "found",
            "source_digest": source, "initial_state_digest": initial,
            "final_state_digest": initial, "actions": [], "explored": 0,
            "budget_exhausted": False,
        }
    if start["state"]["phase"] != "active":
        return {
            "schema_version": SOLVER_SCHEMA, "status": "unreachable",
            "source_digest": source, "initial_state_digest": initial,
            "final_state_digest": None, "actions": [], "explored": 0,
            "budget_exhausted": False,
        }
    remaining = start["world"]["step_limit"] - start["state"]["tick"]
    depth_limit = min(max_depth, remaining)
    frontier: deque[tuple[dict[str, Any], tuple[dict[str, str], ...]]] = deque([
        (start, ()),
    ])
    seen = {_state_key(start["state"])}
    explored = 0
    truncated = False
    while frontier:
        snapshot, actions = frontier.popleft()
        if explored >= max_states:
            truncated = True
            break
        explored += 1
        if len(actions) >= depth_limit:
            if snapshot["state"]["phase"] == "active":
                truncated = True
            continue
        for action in _options(snapshot):
            next_snapshot = _advance(snapshot, action)
            candidate = (*actions, action)
            if next_snapshot["state"]["phase"] == "won":
                return {
                    "schema_version": SOLVER_SCHEMA, "status": "found",
                    "source_digest": source,
                    "initial_state_digest": initial,
                    "final_state_digest": next_snapshot["state_digest"],
                    "actions": list(candidate), "explored": explored,
                    "budget_exhausted": False,
                }
            if next_snapshot["state"]["phase"] != "active":
                continue
            key = _state_key(next_snapshot["state"])
            if key not in seen:
                seen.add(key)
                frontier.append((next_snapshot, candidate))
    return {
        "schema_version": SOLVER_SCHEMA,
        "status": "inconclusive" if truncated else "unreachable",
        "source_digest": source, "initial_state_digest": initial,
        "final_state_digest": None, "actions": [],
        "explored": explored, "budget_exhausted": truncated,
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.game.gameplay.scene_route_solver",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--world-json")
    source.add_argument("--session-json")
    parser.add_argument("--max-states", type=int, default=1024)
    parser.add_argument("--max-depth", type=int, default=64)
    args = parser.parse_args(list(argv))
    try:
        world = (
            original_demo()[0] if args.demo else
            _json(args.world_json, "world")
            if args.world_json is not None else None
        )
        session = (
            _json(args.session_json, "session")
            if args.session_json is not None else None
        )
        result = plan_victory(
            world, session=session,
            max_states=args.max_states, max_depth=args.max_depth,
        )
    except SceneTravelError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
