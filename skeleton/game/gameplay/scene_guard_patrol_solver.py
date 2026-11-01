"""Bounded shortest-action planner for actual replay-verified patrol gameplay.

Search never overrides an authored guard, invents a key or treats an
exhausted search as proof that no route exists.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_guard_patrol import (
    _advance_verified, _bounded,
    new_patrol, normalize_patrol, original_patrol, verify_patrol,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _limit

SCHEMA = "skeleton.scene_guard_patrol_solver.v1"
MAX_NODES = 512
MAX_DEPTH = 32


def legal_actions(session: dict[str, Any]) -> list[dict[str, str]]:
    state = session["state"]
    if state["phase"] != "active":
        return []
    scene = state["scene"]
    room = next(s for s in session["source"]["world"]["scenes"]
                if s["id"] == scene["state"]["scene_id"])
    collected = set(scene["state"]["collected"])
    actions: list[dict[str, str]] = []
    for pickup in room["pickups"]:
        if room["id"] + ":" + pickup["id"] not in collected:
            actions.append({"kind": "collect", "pickup_id": pickup["id"]})
    for exit_data in room["exits"]:
        actions.append({"kind": "travel", "exit_id": exit_data["id"]})
    actions.append({"kind": "wait"})
    return actions


def solve_patrol(source: Any, *, resume: Any = None,
                 max_nodes: int = 256, max_depth: int = 16) -> dict[str, Any]:
    nodes = _limit(max_nodes, "max_nodes", 1, MAX_NODES)
    depth = _limit(max_depth, "max_depth", 1, MAX_DEPTH)
    spec = normalize_patrol(source)
    start = new_patrol(spec) if resume is None else verify_patrol(resume)
    if start["source_digest"] != dig(spec):
        raise SceneTravelError("patrol solver resume source mismatch")
    frontier = deque([(start, [])])
    seen = {(start["state"]["tick"], start["state"]["scene"]["state_digest"])}
    explored = 0
    found: tuple[dict[str, Any], list[dict[str, str]]] | None = None
    while frontier and explored < nodes:
        current, actions = frontier.popleft()
        explored += 1
        if current["state"]["phase"] == "won":
            found = (current, actions)
            break
        if current["state"]["phase"] != "active" or len(actions) >= depth:
            continue
        for action in legal_actions(current):
            try:
                successor = _advance_verified(current, action)
            except SceneTravelError:
                continue
            key = (successor["state"]["tick"],
                   successor["state"]["scene"]["state_digest"])
            if key in seen:
                continue
            seen.add(key)
            frontier.append((successor, [*actions, action]))
    if found is not None:
        verified = verify_patrol(found[0])
        result = {
            "schema_version": SCHEMA, "source_digest": start["source_digest"],
            "initial_state_digest": start["state_digest"],
            "status": "witness", "actions": found[1],
            "final_state_digest": verified["state_digest"],
            "session": verified, "explored": explored,
            "max_nodes": nodes, "max_depth": depth,
        }
    else:
        result = {
            "schema_version": SCHEMA, "source_digest": start["source_digest"],
            "initial_state_digest": start["state_digest"],
            "status": "unproven", "actions": [],
            "final_state_digest": None, "session": None,
            "explored": explored, "max_nodes": nodes, "max_depth": depth,
        }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def verify_witness(source: Any, result: Any, *, resume: Any = None) -> dict[str, Any]:
    _bounded(result)
    if type(result) is not dict or set(result) != {
        "schema_version", "source_digest", "initial_state_digest",
        "status", "actions", "final_state_digest", "session",
        "explored", "max_nodes", "max_depth", "receipt",
    }:
        raise SceneTravelError("invalid patrol solver witness")
    if result["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported patrol solver witness")
    if result["receipt"] != dig({k: v for k, v in result.items() if k != "receipt"}):
        raise SceneTravelError("patrol solver receipt mismatch")
    # Recompute the entire bounded search to prevent forged "shortest" claims.
    expected = solve_patrol(source, resume=resume,
                            max_nodes=result["max_nodes"],
                            max_depth=result["max_depth"])
    if result != expected:
        raise SceneTravelError("patrol solver witness replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-patrol-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--session-json")
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--result-json", required=True)
    for p in (demo, solve):
        p.add_argument("--max-nodes", type=int, default=256)
        p.add_argument("--max-depth", type=int, default=16)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = solve_patrol(original_patrol(), max_nodes=args.max_nodes,
                                  max_depth=args.max_depth)
        elif args.command == "solve":
            source = _strict_json(args.source_json, "patrol source")
            resume = (_strict_json(args.session_json, "patrol save")
                      if args.session_json is not None else None)
            result = solve_patrol(source, resume=resume,
                                  max_nodes=args.max_nodes, max_depth=args.max_depth)
        else:
            source = _strict_json(args.source_json, "patrol source")
            witness = _strict_json(args.result_json, "patrol witness")
            result = verify_witness(source, witness)
        print(_bounded(result).decode("utf-8"))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
