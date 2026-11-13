"""Bounded, replay-proven shortest ending route for authored scene missions.

The search expands only actions accepted by the real mission and scene
engines. Exhaustion is reported as inconclusive, never fabricated proof of
an unreachable authored ending.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_mission import (
    _advance, new_mission, original_mission, resume_mission, verify_mission,
)
from skeleton.game.gameplay.scene_route_solver import _options as scene_options
from skeleton.game.gameplay.scene_travel import SceneTravelError, _json

SCHEMA = "skeleton.scene_mission_route.v1"
MAX_STATES = 4096
MAX_DEPTH = 128


def _key(state: dict[str, Any]) -> tuple[Any, ...]:
    scene = state["scene"]["state"]
    return (
        scene["scene_id"], scene["phase"], scene["tick"],
        tuple(scene["inventory"]), tuple(scene["collected"]),
        tuple(scene["visited"]), tuple(sorted(state["choices"].items())),
        tuple(state["missions"]), state["reputation"], state["phase"],
        state["ending"], state["tick"],
    )


def _options(session: dict[str, Any]) -> list[dict[str, Any]]:
    state, source = session["state"], session["source"]
    if state["phase"] != "active":
        return []
    options = []
    scene = state["scene"]["state"]
    if scene["phase"] == "active":
        options.extend({
            "kind": "scene", "action": action,
        } for action in scene_options(state["scene"]))
        for choice in source["choices"]:
            if (choice["scene_id"] == scene["scene_id"]
                    and choice["id"] not in state["choices"]):
                options.extend({
                    "kind": "choose", "choice_id": choice["id"],
                    "option_id": option["id"],
                } for option in choice["options"])
    else:
        options.extend({
            "kind": "finish", "ending_id": ending["id"],
        } for ending in source["endings"]
            if ending["scene_phase"] == scene["phase"])
    return sorted(options, key=lambda x: json.dumps(x, sort_keys=True))


def plan_ending(
    source: Any = None, *, session: Any = None,
    target_ending: str, max_states: int = 512, max_depth: int = 32,
) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one mission source or saved session")
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid mission route state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid mission route depth budget")
    start = new_mission(source) if session is None else verify_mission(session)
    target_ids = {ending["id"] for ending in start["source"]["endings"]}
    if target_ending not in target_ids:
        raise SceneTravelError("unknown authored mission ending")
    initial = start["state_digest"]
    if start["state"]["phase"] == "finished":
        matched = start["state"]["ending"] == target_ending
        return {
            "schema_version": SCHEMA,
            "status": "found" if matched else "unreachable",
            "source_digest": start["source_digest"],
            "initial_state_digest": initial,
            "final_state_digest": initial if matched else None,
            "target_ending": target_ending,
            "actions": [], "explored": 0, "budget_exhausted": False,
        }
    queue = deque([(start, ())])
    seen = {_key(start["state"])}
    explored = 0
    truncated = False
    while queue:
        if explored >= max_states:
            truncated = True
            break
        snapshot, actions = queue.popleft()
        explored += 1
        if len(actions) >= max_depth:
            if _options(snapshot):
                truncated = True
            continue
        for action in _options(snapshot):
            try:
                next_snapshot = _advance(snapshot, action)
            except SceneTravelError:
                # A candidate is only valid when the canonical engine accepts it.
                continue
            candidate = (*actions, action)
            if (next_snapshot["state"]["phase"] == "finished"
                    and next_snapshot["state"]["ending"] == target_ending):
                return {
                    "schema_version": SCHEMA, "status": "found",
                    "source_digest": start["source_digest"],
                    "initial_state_digest": initial,
                    "final_state_digest": next_snapshot["state_digest"],
                    "target_ending": target_ending,
                    "actions": list(candidate), "explored": explored,
                    "budget_exhausted": False,
                }
            if next_snapshot["state"]["phase"] != "active":
                continue
            key = _key(next_snapshot["state"])
            if key not in seen:
                seen.add(key)
                queue.append((next_snapshot, candidate))
    return {
        "schema_version": SCHEMA,
        "status": "inconclusive" if truncated else "unreachable",
        "source_digest": start["source_digest"],
        "initial_state_digest": initial, "final_state_digest": None,
        "target_ending": target_ending, "actions": [],
        "explored": explored, "budget_exhausted": truncated,
    }


def verify_plan(plan: Any, *, source: Any = None, session: Any = None) -> dict[str, Any]:
    if type(plan) is not dict or plan.get("schema_version") != SCHEMA:
        raise SceneTravelError("invalid mission route receipt")
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one mission source or saved session")
    start = new_mission(source) if session is None else verify_mission(session)
    if (plan.get("source_digest") != start["source_digest"]
            or plan.get("initial_state_digest") != start["state_digest"]):
        raise SceneTravelError("mission route source or initial state mismatch")
    if plan.get("status") != "found":
        raise SceneTravelError("only found mission routes have playable witnesses")
    actions = plan.get("actions")
    if type(actions) is not list or len(actions) > MAX_DEPTH:
        raise SceneTravelError("invalid mission route action list")
    final = resume_mission(start, actions)
    if (final["state"]["phase"] != "finished"
            or final["state"]["ending"] != plan.get("target_ending")
            or final["state_digest"] != plan.get("final_state_digest")):
        raise SceneTravelError("mission route witness does not replay")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-route")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--ending-id", default="lantern_restored")
    parser.add_argument("--max-states", type=int, default=512)
    parser.add_argument("--max-depth", type=int, default=32)
    args = parser.parse_args(list(argv))
    try:
        result = plan_ending(
            original_mission() if args.demo else (
                _json(args.source_json, "mission source")
                if args.source_json is not None else None
            ),
            session=(
                _json(args.session_json, "mission session", max_bytes=2 * 1024 * 1024)
                if args.session_json is not None else None
            ),
            target_ending=args.ending_id,
            max_states=args.max_states, max_depth=args.max_depth,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
