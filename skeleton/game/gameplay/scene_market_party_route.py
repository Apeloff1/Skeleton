"""Replay-proven cooperative market route search with strict turn arbitration.

Search is advisory. Only the canonical party and market reducers can certify
a victory. A bounded miss is inconclusive, never evidence of impossibility.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _json
from skeleton.game.gameplay.scene_market_party import (
    ROLES, _advance, export_party, new_party, original_party, resume_party,
    verify_party,
)
from skeleton.game.gameplay.scene_market_route import _choices, _fingerprint
from skeleton.game.gameplay.scene_tile_walk import MAX_STEPS, _bounded
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_party_route.v1"
MAX_NODES = 1024
MAX_DEPTH = 64
MAX_CANDIDATES = 128


def _budgets(nodes: Any, depth: Any) -> None:
    if type(nodes) is not int or not 1 <= nodes <= MAX_NODES:
        raise SceneTravelError("invalid cooperative route node budget")
    if type(depth) is not int or not 0 <= depth <= MAX_DEPTH:
        raise SceneTravelError("invalid cooperative route depth budget")


def _candidate_turns(session: dict[str, Any]) -> list[dict[str, Any]]:
    state = session["state"]
    if state["market"]["state"]["phase"] != "active":
        return []
    actor = session["source"]["players"][state["turn_index"]]
    allowed = set(actor["roles"])
    market_choices = _choices(state["market"])
    if len(market_choices) > MAX_CANDIDATES:
        raise SceneTravelError("cooperative route action inventory exceeds budget")
    result = [{"player_id": actor["player_id"], "action": {"kind": "pass"}}]
    for action in market_choices:
        required = next((role for role, kind in ROLES.items()
                         if kind == action["kind"]), None)
        if required in allowed:
            result.append({"player_id": actor["player_id"], "action": action})
    return result


def _identity(session: dict[str, Any]) -> str:
    state = session["state"]
    return dig({"market": _fingerprint(state["market"]),
                "actor": state["turn_index"]})


def _report(initial: dict[str, Any], terminal: dict[str, Any] | None,
            turns: list[dict[str, Any]], explored: int, nodes: int,
            depth: int, mode: str, reason: str) -> dict[str, Any]:
    won = terminal is not None and terminal["state"]["market"]["state"]["phase"] == "won"
    bundle = export_party(terminal) if won else None
    result = {
        "schema_version": SCHEMA,
        "status": "proven_win" if won else "inconclusive",
        "reason": "canonical_party_replay" if won else reason,
        "mode": mode,
        "source_digest": initial["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "initial_save_digest": dig(initial["save"]),
        "terminal_state_digest": terminal["state_digest"] if won else None,
        "terminal_save_digest": dig(terminal["save"]) if won else None,
        "portable_checksum": bundle["checksum"] if bundle is not None else None,
        "turns": turns if won else [],
        "turn_count": len(turns) if won else 0,
        "explored_states": explored, "node_budget": nodes,
        "depth_budget": depth,
        "qualification": "replay_integrity_not_identity_authentication",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def _prove(initial: dict[str, Any], terminal: dict[str, Any],
           turns: list[dict[str, Any]], explored: int, nodes: int,
           depth: int, mode: str) -> dict[str, Any]:
    replay = resume_party(initial, turns)
    if replay != terminal or replay["state"]["market"]["state"]["phase"] != "won":
        raise SceneTravelError("cooperative route did not replay to earned victory")
    if verify_party(replay) != replay:
        raise SceneTravelError("cooperative route checkpoint failed verification")
    return _report(initial, replay, turns, explored, nodes, depth, mode, "")


def solve_party_route(checkpoint: Any, *, max_nodes: int = 256,
                      max_depth: int = 48,
                      hint_turns: Any = None) -> dict[str, Any]:
    _budgets(max_nodes, max_depth)
    initial = verify_party(checkpoint)
    phase = initial["state"]["market"]["state"]["phase"]
    if phase == "won":
        return _prove(initial, initial, [], 1, max_nodes, max_depth, "bounded")
    if phase != "active":
        return _report(initial, None, [], 1, max_nodes, max_depth,
                       "bounded", "terminal_checkpoint")
    if hint_turns is not None:
        if type(hint_turns) is not list or len(hint_turns) > max_depth:
            raise SceneTravelError("invalid cooperative route hint length")
        # An untrusted hint is never a proof by itself. Replay the full
        # checkpoint lineage, and reject invalid turns rather than repairing.
        terminal = resume_party(initial, hint_turns)
        return _prove(initial, terminal, hint_turns, 1,
                      max_nodes, max_depth, "hint")
    queue = deque([(initial, [])])
    seen = {_identity(initial)}
    explored = 0
    truncated = False
    while queue:
        if explored >= max_nodes:
            return _report(initial, None, [], explored, max_nodes, max_depth,
                           "bounded", "node_budget_exhausted")
        session, turns = queue.popleft()
        explored += 1
        if len(turns) >= max_depth or session["state"]["sequence"] >= MAX_STEPS:
            truncated = True
            continue
        for turn in _candidate_turns(session):
            try:
                successor = _advance(session, turn)
            except SceneTravelError:
                continue
            path = [*turns, turn]
            if successor["state"]["market"]["state"]["phase"] == "won":
                return _prove(initial, successor, path, explored,
                              max_nodes, max_depth, "bounded")
            if successor["state"]["market"]["state"]["phase"] != "active":
                continue
            identity = _identity(successor)
            if identity in seen:
                continue
            if len(seen) >= max_nodes:
                return _report(initial, None, [], explored, max_nodes, max_depth,
                               "bounded", "frontier_budget_exhausted")
            seen.add(identity)
            queue.append((successor, path))
    return _report(initial, None, [], explored, max_nodes, max_depth,
                   "bounded", "depth_budget_exhausted" if truncated
                   else "no_winning_witness_within_bounds")


def verify_party_route(checkpoint: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid cooperative route report")
    mode = report.get("mode")
    if mode not in ("hint", "bounded"):
        raise SceneTravelError("unsupported cooperative route mode")
    hint = report.get("turns") if mode == "hint" else None
    expected = solve_party_route(
        checkpoint, max_nodes=report.get("node_budget"),
        max_depth=report.get("depth_budget"), hint_turns=hint,
    )
    if expected != report:
        raise SceneTravelError("cooperative route report diverges from replay")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-party-route")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    solve = sub.add_parser("solve")
    verify = sub.add_parser("verify")
    for command in (demo, solve):
        command.add_argument("--max-nodes", type=int, default=256)
        command.add_argument("--max-depth", type=int, default=48)
    solve.add_argument("--session-json", required=True)
    solve.add_argument("--hint-json")
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, turns = original_party()
            result = solve_party_route(
                new_party(source), max_nodes=args.max_nodes,
                max_depth=args.max_depth, hint_turns=turns,
            )
        elif args.command == "solve":
            result = solve_party_route(
                _json(args.session_json), max_nodes=args.max_nodes,
                max_depth=args.max_depth,
                hint_turns=_json(args.hint_json)
                if args.hint_json is not None else None,
            )
        else:
            result = verify_party_route(
                _json(args.session_json), _json(args.report_json),
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
