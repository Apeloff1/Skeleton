"""Bounded tactical control-point solver with independently replayed witnesses.

Only the selected team's decisions are searched. Opponents act through the
canonical deterministic tactical policy. Exhausting a search budget is never
reported as proof of impossibility.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.arena_control import (
    SCHEMA as CONTROL_SCHEMA, _advance_control, _encoded,
    new_control, normalize_control, original_control, verify_control,
)
from skeleton.game.gameplay.arena_policy import _decide
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.tactical_arena import (
    _active, legal_moves, legal_targets,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control_solver.v1"
MAX_NODES = 256
MAX_DEPTH = 8


def _choices(session: dict[str, Any]) -> list[dict[str, Any]]:
    arena = session["arena_session"]
    actor_id, _ = _active(arena["source"], arena["state"])
    options: list[dict[str, Any]] = []
    for target in legal_targets(arena["source"], arena["state"], actor_id):
        options.append({"kind": "attack", "actor_id": actor_id, "target_id": target})
    for direction in legal_moves(arena["source"], arena["state"], actor_id):
        options.append({"kind": "move", "actor_id": actor_id, "direction": direction})
    options.extend([
        {"kind": "guard", "actor_id": actor_id},
        {"kind": "rest", "actor_id": actor_id},
    ])
    return options


def _auto_until_team(session: dict[str, Any], team: str,
                     actions: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Advance only legal canonical opponent actions until a player decision."""
    while session["state"]["phase"] == "active":
        arena = session["arena_session"]
        actor_id, _ = _active(arena["source"], arena["state"])
        actors = {actor["id"]: actor for actor in arena["source"]["actors"]}
        if actors[actor_id]["team"] == team:
            break
        action = _decide(arena)
        session = _advance_control(session, action)
        actions.append(action)
    return session, actions


def _key(session: dict[str, Any]) -> str:
    """Equivalent future states share one search node, regardless of save lineage."""
    arena = session["arena_session"]
    return dig({
        "tick": session["state"]["tick"],
        "phase": session["state"]["phase"],
        "scores": session["state"]["scores"],
        "actors": arena["state"]["actors"],
        "next_index": arena["state"]["next_index"],
        "arena_phase": arena["state"]["phase"],
    })


def solve_control(source: Any, team: Any, *, resume: Any = None,
                  max_nodes: int = MAX_NODES,
                  max_depth: int = MAX_DEPTH) -> dict[str, Any]:
    spec = normalize_control(source)
    selected = _id(team, "team")
    teams = {actor["team"] for actor in spec["arena"]["actors"]}
    if selected not in teams:
        raise CombatSessionError("unknown control-point player team")
    nodes = _integer(max_nodes, "max_nodes", 1, MAX_NODES)
    depth = _integer(max_depth, "max_depth", 0, MAX_DEPTH)
    start = new_control(spec) if resume is None else verify_control(resume)
    if start["source_digest"] != dig(spec):
        raise CombatSessionError("control-point solver source mismatch")
    frontier = deque([(start, [], 0)])
    seen = {_key(start)}
    explored = 0
    solution = None
    while frontier and explored < nodes:
        session, actions, decisions = frontier.popleft()
        explored += 1
        if session["state"]["phase"] == "won" and session["state"]["winner"] == selected:
            solution = (session, actions)
            break
        if session["state"]["phase"] != "active":
            continue
        automatic: list[dict[str, Any]] = []
        session, automatic = _auto_until_team(session, selected, automatic)
        actions = [*actions, *automatic]
        if session["state"]["phase"] == "won" and session["state"]["winner"] == selected:
            solution = (session, actions)
            break
        if session["state"]["phase"] != "active" or decisions >= depth:
            continue
        for action in _choices(session):
            child = _advance_control(session, action)
            key = _key(child)
            if key in seen:
                continue
            seen.add(key)
            frontier.append((child, [*actions, action], decisions + 1))
            if len(frontier) > MAX_NODES * 12:
                raise CombatSessionError("control-point solver queue budget exceeded")
    if solution is None:
        result = {
            "schema_version": SCHEMA, "status": "unproven_within_budget",
            "claim": "bounded_search_not_impossibility_proof",
            "source_digest": dig(spec), "team": selected,
            "start": start, "actions": [], "terminal": None,
            "explored": explored, "max_nodes": nodes, "max_depth": depth,
        }
    else:
        terminal, actions = solution
        # Verify the exact proposed witness from the original saved prefix.
        checked = start
        for action in actions:
            checked = _advance_control(checked, action)
        if checked != terminal:
            raise CombatSessionError("control-point solver witness mismatch")
        result = {
            "schema_version": SCHEMA, "status": "solved",
            "claim": "canonical_replay_verified_witness",
            "source_digest": dig(spec), "team": selected,
            "start": start, "actions": actions, "terminal": terminal,
            "explored": explored, "max_nodes": nodes, "max_depth": depth,
        }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_solution(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "status", "claim", "source_digest", "team",
        "start", "actions", "terminal", "explored", "max_nodes",
        "max_depth", "receipt",
    }, "control-point solver receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported control-point solver receipt")
    _encoded(obj)
    start = verify_control(obj["start"])
    expected = solve_control(
        start["source"], obj["team"], resume=start,
        max_nodes=obj["max_nodes"], max_depth=obj["max_depth"],
    )
    if expected != obj:
        raise CombatSessionError("control-point solver receipt or witness mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Find bounded original canal beacon victory")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--team", required=True)
    solve.add_argument("--resume-json")
    solve.add_argument("--max-nodes", type=int, default=MAX_NODES)
    solve.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = solve_control(original_control(), "wayfarers")
        elif args.command == "solve":
            result = solve_control(
                _parse_json(args.source_json, "control-point source"),
                args.team,
                resume=_parse_json(args.resume_json, "control-point checkpoint")
                if args.resume_json is not None else None,
                max_nodes=args.max_nodes, max_depth=args.max_depth,
            )
        else:
            result = verify_solution(_parse_json(args.receipt_json, "control-point solver receipt"))
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
