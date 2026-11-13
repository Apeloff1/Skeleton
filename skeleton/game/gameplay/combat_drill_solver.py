"""Bounded deterministic combat lesson solver with replayable player witnesses.

This is an offline planning assistant, not a game-state authority. Every
candidate is advanced through the canonical combat engine and enemy policy.
Unknown or exhausted search is reported explicitly, never as a proof of loss.
"""
from __future__ import annotations

import argparse
from collections import deque
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.combat_drill import (
    SCHEMA as DRILL_SCHEMA, _actor_team, _step_unchecked, new_drill,
    original_drill, verify_drill,
)
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.tactical_policy import POLICY_VERSION
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _active_actor, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_drill_solver.v1"
MAX_STATES = 2048
MAX_DEPTH = 8
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _choices(session: dict[str, Any]) -> list[dict[str, str]]:
    """Canonical legal human moves, ordered to prefer shorter attack wins."""
    combat = session["combat"]
    actor_id, _ = _active_actor(combat["scenario"], combat["state"])
    if _actor_team(combat["scenario"], actor_id) != session["source"]["player_team"]:
        raise CombatSessionError("solver encountered opponent-controlled turn")
    enemies = sorted(
        actor["id"] for actor in combat["scenario"]["actors"]
        if actor["team"] != session["source"]["player_team"]
        and combat["state"]["actors"][actor["id"]]["hp"] > 0
    )
    return [
        *[{"kind": "attack", "actor_id": actor_id, "target_id": enemy}
          for enemy in enemies],
        {"kind": "guard", "actor_id": actor_id},
        {"kind": "rest", "actor_id": actor_id},
    ]


def _size(value: Any) -> None:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid solver report JSON") from exc
    if len(encoded) > MAX_REPORT_BYTES:
        raise CombatSessionError("solver report exceeds size budget")


def solve_drill(*, source: Any = None, session: Any = None,
                max_states: int = 512, max_depth: int = 8) -> dict[str, Any]:
    """Find a shortest successful player command path under explicit limits.

    The breadth-first frontier is bounded by max_states; failure to find a
    solution is not an unwinnability certificate. All bot turns are replayable.
    """
    _integer(max_states, "max_states", 1, MAX_STATES)
    _integer(max_depth, "max_depth", 1, MAX_DEPTH)
    if (source is None) == (session is None):
        raise CombatSessionError("provide exactly one of source or session")
    start = new_drill(source) if source is not None else verify_drill(session)
    frontier = deque([(start, [])])
    seen = {start["combat"]["state_digest"]}
    explored = 0
    solution: dict[str, Any] | None = None
    commands: list[dict[str, str]] | None = None
    truncated = False
    while frontier:
        if explored >= max_states:
            truncated = True
            break
        current, path = frontier.popleft()
        explored += 1
        if current["outcome"] == "passed":
            solution, commands = current, path
            break
        if current["outcome"] != "active" or len(path) >= max_depth:
            continue
        for action in _choices(current):
            candidate = _step_unchecked(current, action)
            identity = candidate["combat"]["state_digest"]
            if identity in seen:
                continue
            seen.add(identity)
            frontier.append((candidate, [*path, action]))
    result = {
        "schema_version": SCHEMA,
        "drill_schema": DRILL_SCHEMA,
        "policy_version": POLICY_VERSION,
        "source_digest": start["source_digest"],
        "start_session": start,
        "max_states": max_states,
        "max_depth": max_depth,
        "explored_states": explored,
        "status": (
            "solved" if solution is not None else
            "budget_exhausted" if truncated else "not_found_within_depth"
        ),
        "commands": commands,
        "terminal_session": solution,
    }
    result["receipt"] = dig(result)
    _size(result)
    return result


def verify_solution(raw: Any) -> dict[str, Any]:
    """Recompute the entire bounded search and terminal gameplay receipt."""
    _size(raw)
    obj = _object(raw, {
        "schema_version", "drill_schema", "policy_version", "source_digest",
        "start_session", "max_states", "max_depth", "explored_states",
        "status", "commands", "terminal_session", "receipt",
    }, "solver report")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported solver report schema")
    start = verify_drill(obj["start_session"])
    expected = solve_drill(
        session=start,
        max_states=obj["max_states"],
        max_depth=obj["max_depth"],
    )
    if obj != expected:
        raise CombatSessionError("solver witness, policy or receipt mismatch")
    if expected["terminal_session"] is not None:
        verify_drill(expected["terminal_session"])
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-drill-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Solve original offline combat lesson")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json")
    solve.add_argument("--session-json")
    solve.add_argument("--max-states", type=int, default=512)
    solve.add_argument("--max-depth", type=int, default=8)
    verify = sub.add_parser("verify")
    verify.add_argument("--result-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = solve_drill(source=original_drill())
        elif args.command == "solve":
            if bool(args.source_json) == bool(args.session_json):
                raise CombatSessionError("provide source or session JSON")
            result = solve_drill(
                source=_parse_json(args.source_json, "drill source")
                if args.source_json else None,
                session=_parse_json(args.session_json, "drill session")
                if args.session_json else None,
                max_states=args.max_states,
                max_depth=args.max_depth,
            )
        else:
            result = verify_solution(_parse_json(args.result_json, "solver report"))
        _size(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
