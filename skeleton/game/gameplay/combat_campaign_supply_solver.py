"""Bounded replay-proven planner for the earned-supply combat campaign.

Search is deterministic and returns an explicit inconclusive status when
resources run out; a partial search is never reported as proof of failure.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_campaign_supply import (
    _advance, _encoded, _hero_max, available_supply, new_supply,
    normalize_supply, original_supply, verify_supply,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_campaign_supply_solver.v1"
MAX_STATES = 256
MAX_DEPTH = 16


def _strategic_key(snapshot: dict[str, Any]) -> tuple[Any, ...]:
    state = snapshot["state"]
    return (
        state["phase"], state["encounter_index"], state["hp"],
        state["currency"], state["inventory"]["medkit"],
        state["inventory"]["ward"], state["ward_active"],
    )


def solve_supply(source: Any, *, min_hp: int = 1, max_states: int = 96,
                 max_depth: int = 12) -> dict[str, Any]:
    spec = normalize_supply(source)
    threshold = _integer(min_hp, "minimum victory HP", 1, _hero_max(spec))
    budget = _integer(max_states, "search state budget", 1, MAX_STATES)
    depth = _integer(max_depth, "search depth budget", 1, MAX_DEPTH)
    start = new_supply(spec)
    frontier = deque([(start, [])])
    visited = {_strategic_key(start)}
    expanded = 0
    truncated = False
    winner: tuple[dict[str, Any], list[dict[str, str]]] | None = None
    while frontier:
        if expanded >= budget:
            truncated = True
            break
        snapshot, path = frontier.popleft()
        expanded += 1
        state = snapshot["state"]
        if state["phase"] == "won" and state["hp"] >= threshold:
            winner = snapshot, path
            break
        if state["phase"] != "active":
            continue
        if len(path) >= depth:
            truncated = True
            continue
        for command in available_supply(snapshot)["actions"]:
            candidate = _advance(snapshot, command)
            key = _strategic_key(candidate)
            if key not in visited:
                visited.add(key)
                frontier.append((candidate, [*path, command]))
    status = "found" if winner else ("inconclusive" if truncated else "unreachable")
    result = {
        "schema_version": SCHEMA, "source_digest": dig(spec),
        "min_hp": threshold, "max_states": budget, "max_depth": depth,
        "status": status, "expanded": expanded, "visited": len(visited),
        "actions": winner[1] if winner else [],
        "snapshot": verify_supply(winner[0]) if winner else None,
        "claim": "bounded_offline_replay_only",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_supply_solution(source: Any, raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source_digest", "min_hp", "max_states",
        "max_depth", "status", "expanded", "visited", "actions",
        "snapshot", "claim", "receipt",
    }, "supply solver receipt")
    if obj["schema_version"] != SCHEMA or obj["claim"] != "bounded_offline_replay_only":
        raise CombatSessionError("unsupported supply solver receipt")
    _encoded(obj)
    if obj["receipt"] != dig({k: v for k, v in obj.items() if k != "receipt"}):
        raise CombatSessionError("supply solver receipt digest mismatch")
    expected = solve_supply(
        source, min_hp=obj["min_hp"], max_states=obj["max_states"],
        max_depth=obj["max_depth"],
    )
    if expected != obj:
        raise CombatSessionError("supply solver search or replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-supply-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Find a durable Lantern Harbor survival route")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--receipt-json", required=True)
    for command in (demo, solve):
        command.add_argument("--min-hp", type=int, default=11)
        command.add_argument("--max-states", type=int, default=96)
        command.add_argument("--max-depth", type=int, default=12)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = solve_supply(
                original_supply(), min_hp=args.min_hp,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            source = _parse_json(args.source_json, "supply source")
            if args.command == "solve":
                result = solve_supply(
                    source, min_hp=args.min_hp,
                    max_states=args.max_states, max_depth=args.max_depth,
                )
            else:
                result = verify_supply_solution(
                    source, _parse_json(args.receipt_json, "supply solver receipt"),
                )
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, RecursionError, OverflowError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
