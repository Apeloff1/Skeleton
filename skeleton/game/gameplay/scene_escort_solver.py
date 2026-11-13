"""Bounded legal escort route search with replay-verifiable delivery witnesses.

Search never invents pickups, mission outcomes, or protection. Every edge is
executed by the canonical escort engine. Resource exhaustion is inconclusive,
not proof that an authored mission has no successful route.
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
from skeleton.game.gameplay.scene_escort import (
    MAX_BYTES, _advance, _bounded, export_escort,
    new_escort, normalize_escort_source, original_escort, simulate_escort,
)
from skeleton.game.gameplay.scene_mission_solver import _options as mission_options
from skeleton.game.gameplay.scene_travel import SceneTravelError, _limit

SCHEMA = "skeleton.scene_escort_solver.v1"
MAX_DEPTH = 64
MAX_STATES = 4096


def _key(session: dict[str, Any]) -> str:
    state = session["state"]
    return dig({
        "mission": state["mission"]["state"],
        "integrity": state["integrity"], "supplies": state["supplies"],
        "shielded": state["shielded"], "phase": state["phase"],
    })


def _candidates(session: dict[str, Any]) -> list[dict[str, Any]]:
    state = session["state"]
    if state["phase"] != "active":
        return []
    actions = [
        {"kind": "mission", "action": action}
        for action in mission_options(state["mission"])
    ]
    if state["supplies"] > 0 and not state["shielded"]:
        actions.append({"kind": "protect"})
    return actions


def solve_escort(source: Any, *, max_depth: int = 32,
                 max_states: int = 1024) -> dict[str, Any]:
    _limit(max_depth, "escort solver depth", 1, MAX_DEPTH)
    _limit(max_states, "escort solver state budget", 1, MAX_STATES)
    spec = normalize_escort_source(source)
    initial = new_escort(spec)
    queue = deque([(initial, [])])
    seen = {_key(initial)}
    explored = 0
    truncated = False
    while queue:
        if explored >= max_states:
            truncated = True
            break
        current, actions = queue.popleft()
        explored += 1
        if current["state"]["phase"] == "delivered":
            replay = simulate_escort(spec, actions)
            if replay != current:
                raise SceneTravelError("escort solver witness replay mismatch")
            bundle = export_escort(replay)
            report = {
                "schema_version": SCHEMA, "status": "found",
                "source_digest": initial["source_digest"],
                "actions": actions, "turns": len(actions),
                "explored": explored, "state_digest": replay["state_digest"],
                "bundle": bundle,
            }
            _bounded(report)
            return {**report, "receipt": dig(report)}
        if current["state"]["phase"] != "active":
            continue
        if len(actions) >= max_depth:
            truncated = True
            continue
        for action in _candidates(current):
            try:
                next_session = _advance(current, action)
            except SceneTravelError:
                continue
            key = _key(next_session)
            if key in seen:
                continue
            seen.add(key)
            queue.append((next_session, [*actions, action]))
    report = {
        "schema_version": SCHEMA,
        "status": "inconclusive" if truncated else "unreachable",
        "source_digest": initial["source_digest"], "actions": [],
        "turns": None, "explored": explored,
        "state_digest": None, "bundle": None,
    }
    return {**report, "receipt": dig(report)}


def verify_witness(source: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict or set(report) != {
        "schema_version", "status", "source_digest", "actions",
        "turns", "explored", "state_digest", "bundle", "receipt",
    }:
        raise SceneTravelError("invalid escort solver witness fields")
    if report["schema_version"] != SCHEMA or report["status"] != "found":
        raise SceneTravelError("escort witness is not a found route")
    if report["receipt"] != dig({k: v for k, v in report.items() if k != "receipt"}):
        raise SceneTravelError("escort solver receipt mismatch")
    spec = normalize_escort_source(source)
    if report["source_digest"] != dig(spec):
        raise SceneTravelError("escort solver source mismatch")
    if type(report["actions"]) is not list or len(report["actions"]) > MAX_DEPTH:
        raise SceneTravelError("invalid escort solver witness actions")
    replay = simulate_escort(spec, report["actions"])
    if (replay["state"]["phase"] != "delivered"
            or replay["state_digest"] != report["state_digest"]
            or report["turns"] != len(report["actions"])
            or report["bundle"] != export_escort(replay)):
        raise SceneTravelError("escort solver witness does not replay")
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-escort-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--max-depth", type=int, default=32)
    solve.add_argument("--max-states", type=int, default=1024)
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--witness-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        parse = lambda raw: _strict_json(raw, "escort solver JSON", max_bytes=MAX_BYTES)
        if args.command == "demo":
            result = solve_escort(original_escort())
        elif args.command == "solve":
            result = solve_escort(parse(args.source_json),
                                  max_depth=args.max_depth,
                                  max_states=args.max_states)
        else:
            result = verify_witness(parse(args.source_json), parse(args.witness_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
