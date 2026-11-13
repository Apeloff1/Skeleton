"""Bounded shortest playable combat-contract routes with replay proof.

Breadth-first exploration only uses legal canonical combat actions. Equivalent
gameplay states are deduplicated without trusting journal digests as identity.
The returned route is replayed and exported; failure to prove a route within
the explicit budget is a failure, not an invented victory.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _active_actor, _integer, _parse_json,
)
from skeleton.game.gameplay.combat_contract import (
    MAX_SESSION_BYTES, SCHEMA as CONTRACT_SCHEMA, _advance, _bounded,
    export_contract, new_contract, normalize_contract, original_contract,
    simulate_contract,
)

SCHEMA = "skeleton.combat_contract_solver.v1"
MAX_DEPTH = 16
MAX_NODES = 3000


def _candidates(session: dict[str, Any]) -> list[dict[str, str]]:
    scenario = session["source"]["scenario"]
    combat = session["state"]["combat"]
    actor_id, _ = _active_actor(scenario, combat["state"])
    actors = {actor["id"]: actor for actor in scenario["actors"]}
    team = actors[actor_id]["team"]
    opponents = sorted(
        actor["id"] for actor in scenario["actors"]
        if actor["team"] != team
        and combat["state"]["actors"][actor["id"]]["hp"] > 0
    )
    return [
        *({"kind": "attack", "actor_id": actor_id, "target_id": target}
          for target in opponents),
        {"kind": "guard", "actor_id": actor_id},
        {"kind": "rest", "actor_id": actor_id},
    ]


def _gameplay_key(session: dict[str, Any]) -> str:
    """Include partial guard progress, not just a Boolean earned objective."""
    source = session["source"]
    combat = session["state"]["combat"]
    actor_teams = {actor["id"]: actor["team"]
                   for actor in source["scenario"]["actors"]}
    guards = sum(
        event["action"]["kind"] == "guard"
        and actor_teams[event["action"]["actor_id"]] == source["player_team"]
        for event in combat["journal"]
    )
    guard_threshold = max(
        (obj["minimum"] for obj in source["objectives"]
         if obj["kind"] == "guard"), default=0,
    )
    return dig({
        "combat_state": combat["state"],
        "guard_count": min(guards, guard_threshold),
        "objectives": session["state"]["objectives"],
        "phase": session["state"]["phase"],
    })


def solve_contract(source: Any, *, max_depth: int = MAX_DEPTH,
                   max_nodes: int = MAX_NODES) -> dict[str, Any]:
    spec = normalize_contract(source)
    if len(spec["scenario"]["actors"]) > 4:
        raise CombatSessionError("solver supports at most four combat actors")
    depth = _integer(max_depth, "solver max_depth", 1, MAX_DEPTH)
    nodes = _integer(max_nodes, "solver max_nodes", 1, MAX_NODES)
    start = new_contract(spec)
    queue = deque([start])
    visited = {_gameplay_key(start)}
    expanded = 0
    while queue:
        if expanded >= nodes:
            raise CombatSessionError("combat solver node budget exhausted")
        current = queue.popleft()
        expanded += 1
        if current["state"]["phase"] == "won":
            actions = [event["action"] for event in current["journal"]]
            replay = simulate_contract(spec, actions)
            if replay != current:
                raise CombatSessionError("solver route replay mismatch")
            report = {
                "schema_version": SCHEMA, "source": spec,
                "source_digest": dig(spec), "max_depth": depth,
                "max_nodes": nodes, "expanded": expanded,
                "actions": actions, "session": replay,
                "portable_bundle": export_contract(replay),
            }
            report["receipt"] = dig(report)
            _bounded(report, MAX_SESSION_BYTES)
            return report
        if (current["state"]["phase"] != "active"
                or len(current["journal"]) >= depth):
            continue
        for action in _candidates(current):
            try:
                next_session = _advance(current, action)
            except CombatSessionError:
                continue
            key = _gameplay_key(next_session)
            if key not in visited:
                visited.add(key)
                queue.append(next_session)
                # Count enqueued states too, so a wide frontier is bounded.
                if len(visited) > nodes:
                    raise CombatSessionError("combat solver frontier budget exhausted")
    raise CombatSessionError("no earned contract route within solver budget")


def verify_solution(raw: Any) -> dict[str, Any]:
    _bounded(raw, MAX_SESSION_BYTES)
    if type(raw) is not dict or set(raw) != {
        "schema_version", "source", "source_digest", "max_depth",
        "max_nodes", "expanded", "actions", "session",
        "portable_bundle", "receipt",
    } or raw["schema_version"] != SCHEMA:
        raise CombatSessionError("invalid combat solver report")
    rebuilt = solve_contract(raw["source"], max_depth=raw["max_depth"],
                             max_nodes=raw["max_nodes"])
    if rebuilt != raw:
        raise CombatSessionError("combat solver replay or route mismatch")
    return rebuilt


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-contract-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    run = sub.add_parser("run")
    run.add_argument("--source-json", required=True)
    for p in (demo, run):
        p.add_argument("--max-depth", type=int, default=MAX_DEPTH)
        p.add_argument("--max-nodes", type=int, default=MAX_NODES)
    sub.add_parser("verify").add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "verify":
            result = verify_solution(_parse_json(args.report_json, "solver report"))
        else:
            source = (original_contract() if args.command == "demo"
                      else _parse_json(args.source_json, "contract source"))
            result = solve_contract(
                source, max_depth=args.max_depth, max_nodes=args.max_nodes,
            )
        _bounded(result, MAX_SESSION_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            RecursionError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
