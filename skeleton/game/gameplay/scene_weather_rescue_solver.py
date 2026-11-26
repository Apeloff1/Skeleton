"""Bounded replay-proven weather/NPC rescue planning with safe failure claims."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _json, _limit, _object,
)
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_rescue import (
    _advance, new_rescue, normalize_rescue, original_rescue,
    verify_rescue,
)

SCHEMA = "skeleton.weather_rescue_solver.v1"
MAX_NODES = 256
MAX_DEPTH = 16


def _choices(session: dict[str, Any]) -> list[dict[str, Any]]:
    state = session["state"]
    weather = session["weather_session"]
    scene = weather["state"]["scene"]["state"]
    scene_id = scene["scene_id"]
    source = session["source"]
    options = []
    for npc in source["npcs"]:
        status = state["npcs"][npc["npc_id"]]["status"]
        if status == "waiting" and scene_id == npc["origin_scene"]:
            options.append({"kind": "rescue", "npc_id": npc["npc_id"]})
        if status == "escorting" and scene_id == npc["shelter_scene"]:
            options.append({"kind": "shelter", "npc_id": npc["npc_id"]})
    current = next(
        item for item in source["weather"]["world"]["scenes"]
        if item["id"] == scene_id
    )
    collected = set(scene["collected"])
    for pickup in current["pickups"]:
        if scene_id + ":" + pickup["id"] not in collected:
            options.append({"kind": "weather", "action": {
                "kind": "scene", "action": {
                    "kind": "collect", "pickup_id": pickup["id"],
                },
            }})
    for edge in current["exits"]:
        options.append({"kind": "weather", "action": {
            "kind": "scene", "action": {
                "kind": "travel", "exit_id": edge["id"],
            },
        }})
    options.append({"kind": "weather", "action": {"kind": "wait"}})
    return options


def _key(session: dict[str, Any]) -> str:
    weather = session["weather_session"]
    return dig({
        "tick": session["state"]["tick"],
        "phase": session["state"]["phase"],
        "earned": session["state"]["earned"],
        "npcs": session["state"]["npcs"],
        "weather": weather["state"]["weather"],
        "scene": weather["state"]["scene"]["state"],
    })


def solve_rescue(source: Any, *, resume: Any = None,
                 max_nodes: int = MAX_NODES,
                 max_depth: int = MAX_DEPTH) -> dict[str, Any]:
    spec = normalize_rescue(source)
    nodes = _limit(max_nodes, "max_nodes", 1, MAX_NODES)
    depth = _limit(max_depth, "max_depth", 0, MAX_DEPTH)
    start = new_rescue(spec) if resume is None else verify_rescue(resume)
    if start["source_digest"] != dig(spec):
        raise SceneTravelError("rescue solver source mismatch")
    frontier = deque([(start, [])])
    seen = {_key(start)}
    explored = 0
    solution = None
    while frontier and explored < nodes:
        session, actions = frontier.popleft()
        explored += 1
        if session["state"]["phase"] == "won":
            solution = (session, actions)
            break
        if session["state"]["phase"] != "active" or len(actions) >= depth:
            continue
        for action in _choices(session):
            try:
                child = _advance(session, action)
            except SceneTravelError:
                continue
            key = _key(child)
            if key in seen:
                continue
            seen.add(key)
            frontier.append((child, [*actions, action]))
            if len(frontier) > MAX_NODES * 12:
                raise SceneTravelError("rescue solver queue budget exceeded")
    if solution is None:
        result = {
            "schema_version": SCHEMA, "status": "unproven_within_budget",
            "claim": "bounded_search_not_impossibility_proof",
            "source_digest": dig(spec), "start": start,
            "actions": [], "terminal": None,
            "explored": explored, "max_nodes": nodes, "max_depth": depth,
        }
    else:
        terminal, actions = solution
        checked = start
        for action in actions:
            checked = _advance(checked, action)
        if checked != terminal:
            raise SceneTravelError("rescue solver witness mismatch")
        result = {
            "schema_version": SCHEMA, "status": "solved",
            "claim": "canonical_replay_verified_witness",
            "source_digest": dig(spec), "start": start,
            "actions": actions, "terminal": terminal,
            "explored": explored, "max_nodes": nodes, "max_depth": depth,
        }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_solution(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "status", "claim", "source_digest",
        "start", "actions", "terminal", "explored",
        "max_nodes", "max_depth", "receipt",
    }, "rescue solver receipt")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported rescue solver receipt")
    _export(obj)
    start = verify_rescue(obj["start"])
    expected = solve_rescue(
        start["source"], resume=start,
        max_nodes=obj["max_nodes"], max_depth=obj["max_depth"],
    )
    if expected != obj:
        raise SceneTravelError("rescue solver receipt mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-rescue-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Find a replayable original NPC shelter route")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--resume-json")
    solve.add_argument("--max-nodes", type=int, default=MAX_NODES)
    solve.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_rescue()
            result = solve_rescue(source)
        elif args.command == "solve":
            result = solve_rescue(
                _json(args.source_json, "rescue source"),
                resume=_json(args.resume_json, "rescue checkpoint")
                if args.resume_json is not None else None,
                max_nodes=args.max_nodes, max_depth=args.max_depth,
            )
        else:
            result = verify_solution(_json(args.receipt_json, "rescue solver receipt"))
        print(_export(result))
        return 0 if result["status"] == "solved" else 3
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
