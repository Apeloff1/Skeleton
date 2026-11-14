"""Bounded deterministic route planning for canonical weather deliveries.

A solved route is a replayable witness, not a guessed path. Search exhaustion
is explicitly inconclusive; the planner never bypasses weather, item or
deadline checks and never treats unverified client score as an achievement.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _json, _limit, _object
from skeleton.game.gameplay.scene_weather import _export
from skeleton.game.gameplay.scene_weather_delivery import (
    _advance, _statuses, new_deliveries, original_deliveries,
    package_deliveries, resume_deliveries, verify_deliveries,
)
from skeleton.game.gameplay.scene_weather_solver import _actions

SCHEMA = "skeleton.weather_deliveries_route.v1"
MAX_STATES = 256
MAX_DEPTH = 32


def _identity(session: dict[str, Any]) -> str:
    """Ignore journal lineage for safe state deduplication, not for receipts."""
    return dig({
        "weather": session["weather_session"]["state"],
        "statuses": _statuses(session["state"]["journal"]),
        "earned": session["state"]["earned"],
        "phase": session["state"]["phase"],
    })


def _report(start: dict[str, Any], status: str, complete: bool, explored: int,
            actions: list[dict[str, Any]], terminal: dict[str, Any] | None,
            max_states: int, max_depth: int) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "status": status, "complete": complete,
        "explored": explored, "max_states": max_states, "max_depth": max_depth,
        "source_digest": start["source_digest"],
        "start_state_digest": start["state_digest"], "start_session": start,
        "actions": actions,
        "terminal_package": (
            None if terminal is None else package_deliveries(terminal)
        ),
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def plan_deliveries(source: Any = None, *, session: Any = None,
                    max_states: int = 128, max_depth: int = 16) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one delivery source or checkpoint")
    _limit(max_states, "max_states", 1, MAX_STATES)
    _limit(max_depth, "max_depth", 0, MAX_DEPTH)
    start = new_deliveries(source) if session is None else verify_deliveries(session)
    phase = start["state"]["phase"]
    if phase == "won":
        return _report(start, "solved", True, 1, [], start,
                       max_states, max_depth)
    if phase != "active":
        return _report(start, "unreachable", True, 1, [], None,
                       max_states, max_depth)

    frontier = deque([(start, [])])
    seen = {_identity(start)}
    explored = 0
    truncated = False
    while frontier:
        node, path = frontier.popleft()
        explored += 1
        if len(path) >= max_depth:
            truncated = True
            continue
        for action in _actions(node["weather_session"]):
            try:
                next_session = _advance(node, action)
            except SceneTravelError:
                # Invalid travel, blocked weather or exhausted inventory is not a path.
                continue
            witness = [*path, action]
            if next_session["state"]["phase"] == "won":
                replayed = resume_deliveries(start, witness)
                if (replayed != next_session
                        or verify_deliveries(replayed) != next_session):
                    raise SceneTravelError("delivery route witness replay mismatch")
                return _report(start, "solved", True, explored, witness,
                               replayed, max_states, max_depth)
            if next_session["state"]["phase"] != "active":
                continue
            identity = _identity(next_session)
            if identity in seen:
                continue
            if len(seen) >= max_states:
                truncated = True
                continue
            seen.add(identity)
            frontier.append((next_session, witness))
    return _report(
        start, "inconclusive" if truncated else "unreachable",
        not truncated, explored, [], None, max_states, max_depth,
    )


def verify_delivery_route(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "status", "complete", "explored",
        "max_states", "max_depth", "source_digest", "start_state_digest",
        "start_session", "actions", "terminal_package", "receipt",
    }, "delivery route report")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported delivery route report")
    _export(obj)
    start = verify_deliveries(obj["start_session"])
    expected = plan_deliveries(
        session=start, max_states=obj["max_states"], max_depth=obj["max_depth"],
    )
    if expected != obj:
        raise SceneTravelError("delivery route witness or report mismatch")
    return expected


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton weather-deliveries-plan")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    solve = sub.add_parser("solve")
    selector = solve.add_mutually_exclusive_group(required=True)
    selector.add_argument("--source-json")
    selector.add_argument("--session-json")
    solve.add_argument("--max-states", type=int, default=128)
    solve.add_argument("--max-depth", type=int, default=16)
    verify = sub.add_parser("verify")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_deliveries()
            result = plan_deliveries(source)
        elif args.command == "verify":
            result = verify_delivery_route(_json(args.report_json, "delivery route"))
        else:
            source = (_json(args.source_json, "delivery source")
                      if args.source_json is not None else None)
            session = (_json(args.session_json, "delivery save")
                       if args.session_json is not None else None)
            result = plan_deliveries(
                source, session=session,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
