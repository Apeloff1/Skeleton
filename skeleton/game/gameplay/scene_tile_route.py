"""Bounded shortest playable routes through authored tile collision geometry.

A route witness consists only of canonical movement, pickup and exit actions.
Search exhaustion is explicitly inconclusive, never an impossibility proof.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_tile_walk import (
    DIRECTIONS, _advance, _area, export_tiles, import_tiles,
    new_tiles, original_tiles, resume_tiles, verify_tiles,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_tile_route.v1"
MAX_STATES = 2048
MAX_DEPTH = 64


def _limits(max_states: int, max_depth: int) -> None:
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid tile route state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid tile route depth budget")


def legal_tile_actions(session: Any) -> list[dict[str, str]]:
    current = verify_tiles(session)
    state = current["state"]
    if state["phase"] != "active" or state["tick"] >= current["source"]["step_limit"]:
        return []
    scene = state["scene"]["state"]
    area = _area(current["source"], scene["scene_id"])
    x, y = state["position"]
    candidates: list[dict[str, str]] = []
    for direction, (dx, dy) in DIRECTIONS.items():
        nxt = [x + dx, y + dy]
        if (0 <= nxt[0] < area["width"]
                and 0 <= nxt[1] < area["height"]
                and nxt not in area["walls"]):
            candidates.append({"kind": "move", "direction": direction})
    for pickup in area["pickups"]:
        key = scene["scene_id"] + ":" + pickup["id"]
        if pickup["at"] == state["position"] and key not in scene["collected"]:
            candidates.append({"kind": "collect", "pickup_id": pickup["id"]})
    authored = next(s for s in current["source"]["world"]["scenes"]
                    if s["id"] == scene["scene_id"])
    exits = {edge["id"]: edge for edge in authored["exits"]}
    for edge in area["exits"]:
        required = exits[edge["id"]]["requires_item"]
        if (edge["at"] == state["position"]
                and (required is None or required in scene["inventory"])):
            candidates.append({"kind": "travel", "exit_id": edge["id"]})
    return sorted(candidates, key=lambda a: json.dumps(a, sort_keys=True))


def _signature(session: dict[str, Any]) -> str:
    state = session["state"]
    scene = state["scene"]["state"]
    return json.dumps({
        "position": state["position"], "phase": state["phase"],
        "outer_tick": state["tick"], "scene_id": scene["scene_id"],
        "scene_tick": scene["tick"], "inventory": scene["inventory"],
        "collected": scene["collected"],
    }, sort_keys=True, separators=(",", ":"))


def _result(start: dict[str, Any], target: str, status: str,
            actions: list[dict[str, str]], explored: int,
            truncated: bool, final: dict[str, Any] | None,
            max_states: int, max_depth: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "target_phase": target, "status": status,
        "actions": actions, "explored": explored,
        "budget_exhausted": truncated,
        "max_states": max_states, "max_depth": max_depth,
        "final_state_digest": final["state_digest"] if final is not None else None,
        "portable_checksum": (
            export_tiles(final)["checksum"] if final is not None else None
        ),
    }


def solve_tiles(source: Any = None, *, session: Any = None,
                target_phase: str = "won", max_states: int = 512,
                max_depth: int = 24) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one tile source or checkpoint")
    _limits(max_states, max_depth)
    if target_phase not in ("won", "lost") or type(target_phase) is not str:
        raise SceneTravelError("invalid tile target phase")
    start = new_tiles(source) if session is None else verify_tiles(session)
    if start["state"]["phase"] != "active":
        matched = start["state"]["phase"] == target_phase
        return _result(start, target_phase,
                       "found" if matched else "unreachable", [],
                       0, False, start if matched else None,
                       max_states, max_depth)
    queue = deque([(start, ())])
    seen = {_signature(start)}
    explored = 0
    truncated = False
    while queue:
        if explored >= max_states:
            truncated = True
            break
        current, actions = queue.popleft()
        explored += 1
        if len(actions) >= max_depth:
            if legal_tile_actions(current):
                truncated = True
            continue
        for action in legal_tile_actions(current):
            try:
                next_state = _advance(current, action)
            except SceneTravelError:
                continue
            path = (*actions, action)
            if next_state["state"]["phase"] == target_phase:
                bundle = export_tiles(next_state)
                if import_tiles(bundle) != next_state:
                    raise SceneTravelError("tile route portable witness mismatch")
                return _result(start, target_phase, "found", list(path),
                               explored, False, next_state, max_states, max_depth)
            if next_state["state"]["phase"] != "active":
                continue
            signature = _signature(next_state)
            if signature not in seen:
                seen.add(signature)
                queue.append((next_state, path))
    return _result(start, target_phase,
                   "inconclusive" if truncated else "unreachable",
                   [], explored, truncated, None, max_states, max_depth)


def verify_plan(payload: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != {
        "schema_version", "source_digest", "initial_state_digest",
        "target_phase", "status", "actions", "explored", "budget_exhausted",
        "max_states", "max_depth", "final_state_digest", "portable_checksum",
    } or payload["schema_version"] != SCHEMA or payload["status"] != "found":
        raise SceneTravelError("invalid or non-playable tile route witness")
    _limits(payload["max_states"], payload["max_depth"])
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one tile source or checkpoint")
    start = new_tiles(source) if session is None else verify_tiles(session)
    expected = solve_tiles(
        session=start, target_phase=payload["target_phase"],
        max_states=payload["max_states"], max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise SceneTravelError("tile route search receipt mismatch")
    final = resume_tiles(start, payload["actions"])
    if (final["state"]["phase"] != payload["target_phase"]
            or final["state_digest"] != payload["final_state_digest"]
            or export_tiles(final)["checksum"] != payload["portable_checksum"]):
        raise SceneTravelError("tile route gameplay replay mismatch")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-tiles-route")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--target", choices=("won", "lost"), default="won")
    parser.add_argument("--max-states", type=int, default=512)
    parser.add_argument("--max-depth", type=int, default=24)
    parser.add_argument("--verify-json")
    args = parser.parse_args(list(argv))
    try:
        from skeleton.game.gameplay.scene_tile_walk import _json
        source = (original_tiles()[0] if args.demo else
                  _json(args.source_json) if args.source_json is not None else None)
        session = (_json(args.session_json)
                   if args.session_json is not None else None)
        if args.verify_json is not None:
            final = verify_plan(_json(args.verify_json),
                                source=source, session=session)
            result = {"ok": True, "state_digest": final["state_digest"],
                      "phase": final["state"]["phase"]}
        else:
            result = solve_tiles(
                source, session=session, target_phase=args.target,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, TypeError, KeyError, ValueError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
