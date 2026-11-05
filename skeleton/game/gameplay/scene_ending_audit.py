"""Bounded replay-proven authored scene ending and reachability audit.

This is a deterministic offline gameplay QA tool. A missing ending is not
declared impossible if a state/depth budget prevented complete exploration.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_route_solver import _options
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance, _json, new_session, original_demo,
    verify_session,
)

SCHEMA = "skeleton.scene_ending_audit.v1"
MAX_STATES = 4096
MAX_DEPTH = 512


def _key(state: dict[str, Any]) -> tuple[Any, ...]:
    # Unlike victory-only shortest-route search, a draw depends on tick.
    return (
        state["scene_id"], tuple(state["inventory"]),
        tuple(state["collected"]), state["tick"],
    )


def audit_endings(world: Any = None, *, session: Any = None,
                  max_states: int = 512, max_depth: int = 32) -> dict[str, Any]:
    """Find real ending witnesses, recording budget truncation honestly."""
    if (world is None) == (session is None):
        raise SceneTravelError("supply exactly one world or saved session")
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid ending audit state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid ending audit depth budget")
    start = new_session(world) if session is None else verify_session(session)
    source = start["source_digest"]
    initial = start["state_digest"]
    queue = deque([(start, ())])
    visited = {_key(start["state"])}
    reached_scenes = {start["state"]["scene_id"]}
    endings: dict[str, dict[str, Any]] = {}
    explored = 0
    truncated = False
    while queue:
        snapshot, actions = queue.popleft()
        if explored >= max_states:
            truncated = True
            break
        explored += 1
        state = snapshot["state"]
        reached_scenes.add(state["scene_id"])
        if state["phase"] != "active":
            if state["phase"] not in endings:
                endings[state["phase"]] = {
                    "phase": state["phase"], "ending": state["ending"],
                    "scene_id": state["scene_id"],
                    "actions": list(actions),
                    "final_state_digest": snapshot["state_digest"],
                    "turns_from_start": len(actions),
                }
            continue
        if len(actions) >= max_depth:
            if _options(snapshot):
                truncated = True
            continue
        for action in _options(snapshot):
            next_snapshot = _advance(snapshot, action)
            key = _key(next_snapshot["state"])
            if key not in visited:
                visited.add(key)
                queue.append((next_snapshot, (*actions, action)))
    missing = sorted(
        scene["id"] for scene in start["world"]["scenes"]
        if scene["id"] not in reached_scenes
    )
    return {
        "schema_version": SCHEMA,
        "source_digest": source,
        "initial_state_digest": initial,
        "explored_states": explored,
        "state_budget": max_states, "depth_budget": max_depth,
        "budget_exhausted": truncated,
        "coverage": "inconclusive" if truncated else "complete",
        "reachable_scenes": sorted(reached_scenes),
        "unobserved_scenes": missing,
        "endings": {
            name: {
                "status": "found" if name in endings else (
                    "inconclusive" if truncated else "not_reached"
                ),
                "witness": endings.get(name),
            }
            for name in ("won", "lost", "draw")
        },
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.game.gameplay.scene_ending_audit"
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--world-json")
    source.add_argument("--session-json")
    parser.add_argument("--max-states", type=int, default=512)
    parser.add_argument("--max-depth", type=int, default=32)
    args = parser.parse_args(list(argv))
    try:
        world = (
            original_demo()[0] if args.demo else
            _json(args.world_json, "world")
            if args.world_json is not None else None
        )
        saved = (
            _json(args.session_json, "session")
            if args.session_json is not None else None
        )
        result = audit_endings(
            world, session=saved,
            max_states=args.max_states, max_depth=args.max_depth,
        )
    except SceneTravelError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
