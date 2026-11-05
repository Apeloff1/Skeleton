"""Bounded deterministic NPC encounter route solver with replayable witness.

Search explores only legal canonical gameplay transitions. No route is accepted
without an actual terminal scene, authored dialogue consequence and ending.
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
from skeleton.game.gameplay.scene_npc_encounter import (
    MAX_SAVE_BYTES, _size, _step, new_encounter, normalize_encounter,
    original_encounter, verify_encounter,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _limit, _object,
)

SCHEMA = "skeleton.scene_npc_solution.v1"
MAX_NODES = 1024
MAX_DEPTH = 64


def _candidates(session: dict[str, Any], ending_id: str) -> list[dict[str, Any]]:
    spec = session["source"]
    state = session["state"]
    scene_state = state["scene"]["state"]
    if scene_state["phase"] != "active":
        return [{"kind": "finish", "ending_id": ending_id}]
    scene_id = scene_state["scene_id"]
    tick = state["tick"]
    candidates: list[dict[str, Any]] = []
    for npc in spec["npcs"]:
        if npc["id"] not in state["choices"] and npc["route"][tick % len(npc["route"])] == scene_id:
            for offer in npc["offers"]:
                candidates.append({
                    "kind": "talk", "npc_id": npc["id"], "offer_id": offer["id"],
                })
    scene = next(item for item in spec["world"]["scenes"]
                 if item["id"] == scene_id)
    for pickup in scene["pickups"]:
        if scene_id + ":" + pickup["id"] not in scene_state["collected"]:
            candidates.append({
                "kind": "scene", "action": {
                    "kind": "collect", "pickup_id": pickup["id"],
                },
            })
    for edge in scene["exits"]:
        if edge["requires_item"] is None or edge["requires_item"] in scene_state["inventory"]:
            candidates.append({
                "kind": "scene", "action": {
                    "kind": "travel", "exit_id": edge["id"],
                },
            })
    return candidates


def _key(session: dict[str, Any]) -> str:
    """Deduplicate semantically equivalent positions, preserving time."""
    state = session["state"]
    scene = state["scene"]["state"]
    return dig({
        "tick": state["tick"], "scene_id": scene["scene_id"],
        "scene_phase": scene["phase"], "collected": scene["collected"],
        "choices": state["choices"], "flags": state["flags"],
        "reputation": state["reputation"], "ending": state["ending"],
    })


def solve_encounter(
    source: Any, ending_id: str, *,
    max_nodes: int = 256, max_depth: int = 24,
) -> dict[str, Any]:
    spec = normalize_encounter(source)
    target = _id(ending_id, "ending id")
    if target not in {item["id"] for item in spec["endings"]}:
        raise SceneTravelError("NPC solver target ending not authored")
    _limit(max_nodes, "max_nodes", 1, MAX_NODES)
    _limit(max_depth, "max_depth", 1, MAX_DEPTH)
    initial = new_encounter(spec)
    queue = deque([(initial, [])])
    seen = {_key(initial)}
    explored = 0
    while queue:
        if explored >= max_nodes:
            raise SceneTravelError("NPC solver node budget exhausted")
        snapshot, actions = queue.popleft()
        explored += 1
        if snapshot["state"]["phase"] == "finished":
            if snapshot["state"]["ending"] == target:
                session = verify_encounter(snapshot)
                record = {
                    "schema_version": SCHEMA,
                    "source": spec, "source_digest": session["source_digest"],
                    "ending_id": target, "max_nodes": max_nodes,
                    "max_depth": max_depth, "explored_nodes": explored,
                    "actions": actions, "session": session,
                }
                record["receipt"] = dig(record)
                _size(record, MAX_SAVE_BYTES)
                return record
            continue
        if len(actions) >= max_depth:
            continue
        for action in _candidates(snapshot, target):
            try:
                next_session = _step(snapshot, action)
            except SceneTravelError:
                continue
            key = _key(next_session)
            if key in seen:
                continue
            seen.add(key)
            queue.append((next_session, [*actions, action]))
    raise SceneTravelError("NPC ending unreachable within bounded search")


def verify_solution(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_SAVE_BYTES)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "ending_id",
        "max_nodes", "max_depth", "explored_nodes", "actions",
        "session", "receipt",
    }, "NPC solver receipt")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported NPC solver receipt")
    if type(obj["receipt"]) is not str or len(obj["receipt"]) != 64:
        raise SceneTravelError("invalid NPC solver checksum")
    if dig({k: v for k, v in obj.items() if k != "receipt"}) != obj["receipt"]:
        raise SceneTravelError("NPC solver checksum mismatch")
    rebuilt = solve_encounter(
        obj["source"], obj["ending_id"],
        max_nodes=obj["max_nodes"], max_depth=obj["max_depth"],
    )
    if rebuilt != obj:
        raise SceneTravelError("NPC solver witness or shortest route mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-npc-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Solve original NPC dialogue and scene route")
    solve = sub.add_parser("solve", help="Find a bounded legal ending route")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--ending-id", required=True)
    solve.add_argument("--max-nodes", type=int, default=256)
    solve.add_argument("--max-depth", type=int, default=24)
    verify = sub.add_parser("verify", help="Replay-check the shortest-route witness")
    verify.add_argument("--receipt-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = solve_encounter(original_encounter(), "rescued")
        elif args.command == "solve":
            result = solve_encounter(
                _strict_json(args.source_json, "NPC solver source"),
                args.ending_id, max_nodes=args.max_nodes,
                max_depth=args.max_depth,
            )
        else:
            result = verify_solution(_strict_json(args.receipt_json, "NPC solver receipt"))
        _size(result, MAX_SAVE_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
