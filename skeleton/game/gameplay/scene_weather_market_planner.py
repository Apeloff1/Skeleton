"""Bounded, replay-proven route optimization for weather caravan trade.

Unlike a shortest-path-only solver, this planner ranks *actually earned*
canonical net payouts and early-delivery reputation. Exhausted searches are
explicitly inconclusive and cannot claim globally optimal or safe routes.
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
from skeleton.game.gameplay.scene_weather_delivery import _statuses
from skeleton.game.gameplay.scene_weather_solver import _actions
from skeleton.game.gameplay.scene_weather_market import (
    _advance, new_market, original_market, package_market,
    resume_market, verify_market,
)

SCHEMA = "skeleton.weather_market_route.v1"
MAX_STATES = 128
MAX_DEPTH = 16


def _identity(snapshot: dict[str, Any]) -> str:
    """Deduplicate playable states, not save histories or receipts."""
    return dig({
        "weather": snapshot["delivery_session"]["weather_session"]["state"],
        "delivery_statuses": _statuses(
            snapshot["delivery_session"]["state"]["journal"],
        ),
        "gross": snapshot["state"]["gross"],
        "fees": snapshot["state"]["fees"],
        "net": snapshot["state"]["net"],
        "reputation": snapshot["state"]["reputation"],
        "phase": snapshot["state"]["phase"],
    })


def _score(snapshot: dict[str, Any], actions: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Prefer higher net, then reputation, then fewer legal actions."""
    state = snapshot["state"]
    return (state["net"], state["reputation"], -len(actions))


def _report(start: dict[str, Any], status: str, complete: bool,
            explored: int, visited: int, actions: list[dict[str, Any]],
            terminal: dict[str, Any] | None,
            max_states: int, max_depth: int) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA,
        "status": status, "complete": complete,
        "explored": explored, "visited": visited,
        "max_states": max_states, "max_depth": max_depth,
        "source_digest": start["source_digest"],
        "start_state_digest": start["state_digest"],
        "start_session": start,
        "actions": actions,
        "terminal_package": (
            None if terminal is None else package_market(terminal)
        ),
        "objective": "maximize_verified_net_then_reputation_then_minimize_steps",
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def plan_market(source: Any = None, *, session: Any = None,
                max_states: int = 128, max_depth: int = 16) -> dict[str, Any]:
    """Search legal actions without bypassing canonical weather or settlement."""
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one market source or checkpoint")
    _limit(max_states, "max_states", 1, MAX_STATES)
    _limit(max_depth, "max_depth", 0, MAX_DEPTH)
    start = new_market(source) if session is None else verify_market(session)
    phase = start["state"]["phase"]
    if phase == "won":
        return _report(start, "optimal_within_bounds", True, 1, 1, [], start,
                       max_states, max_depth)
    if phase != "active":
        return _report(start, "unreachable", True, 1, 1, [], None,
                       max_states, max_depth)

    frontier = deque([(start, [])])
    seen = {_identity(start)}
    explored = 0
    truncated = False
    best: tuple[dict[str, Any], list[dict[str, Any]]] | None = None
    while frontier:
        node, path = frontier.popleft()
        explored += 1
        if len(path) >= max_depth:
            truncated = True
            continue
        for action in _actions(node["delivery_session"]["weather_session"]):
            try:
                successor = _advance(node, action)
            except SceneTravelError:
                # Weather, collision, item, deadline and budget holds stay intact.
                continue
            witness = [*path, action]
            if successor["state"]["phase"] == "won":
                if best is None or _score(successor, witness) > _score(*best):
                    best = (successor, witness)
                continue
            if successor["state"]["phase"] != "active":
                continue
            identity = _identity(successor)
            if identity in seen:
                continue
            if len(seen) >= max_states:
                truncated = True
                continue
            seen.add(identity)
            frontier.append((successor, witness))

    if best is None:
        return _report(
            start, "inconclusive" if truncated else "unreachable",
            not truncated, explored, len(seen), [], None,
            max_states, max_depth,
        )
    terminal, actions = best
    replayed = resume_market(start, actions)
    if replayed != terminal or verify_market(replayed) != terminal:
        raise SceneTravelError("weather market route witness replay mismatch")
    return _report(
        start, "feasible_unproven" if truncated else "optimal_within_bounds",
        not truncated, explored, len(seen), actions, replayed,
        max_states, max_depth,
    )


def verify_market_route(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "status", "complete", "explored", "visited",
        "max_states", "max_depth", "source_digest", "start_state_digest",
        "start_session", "actions", "terminal_package", "objective",
        "receipt",
    }, "weather market route report")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather market route schema")
    _export(obj)
    expected = plan_market(
        session=obj["start_session"], max_states=obj["max_states"],
        max_depth=obj["max_depth"],
    )
    if expected != obj:
        raise SceneTravelError("weather market route proof mismatch")
    return expected


def cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton weather-market-plan",
        description="Find replay-verified profitable offline caravan routes",
    )
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
            source, _ = original_market()
            result = plan_market(source)
        elif args.command == "verify":
            result = verify_market_route(_json(args.report_json, "market route"))
        else:
            source = (_json(args.source_json, "market source")
                      if args.source_json is not None else None)
            session = (_json(args.session_json, "market save")
                       if args.session_json is not None else None)
            result = plan_market(
                source, session=session, max_states=args.max_states,
                max_depth=args.max_depth,
            )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
