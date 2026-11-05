"""Bounded contract campaign route discovery with canonical replay witnesses.

Failure to find a winning route under a budget is inconclusive, not proof that
an authored market game is impossible. All proposed moves use real reducers.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import _bounded, _json
from skeleton.game.gameplay.scene_market_contract import (
    _advance, new_contract, normalize_contract_source, original_contract,
    simulate_contract, verify_contract,
)
from skeleton.game.gameplay.scene_market_route import _choices
from skeleton.game.gameplay.scene_travel import SceneTravelError, _limit

SCHEMA = "skeleton.scene_market_contract_route.v1"
MAX_NODES = 4096
MAX_DEPTH = 64


def _result(source: dict[str, Any], status: str, nodes: int,
            actions: list[dict[str, Any]] | None) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema_version": SCHEMA, "source_digest": dig(source),
        "status": status, "visited_nodes": nodes,
        "actions": actions, "terminal_state_digest": None,
        "score": None, "qualification": "offline_replay_witness_only",
    }
    if actions is not None:
        terminal = verify_contract(simulate_contract(source, actions))
        if terminal["state"]["phase"] != "won":
            raise SceneTravelError("contract solver witness not winning")
        report["terminal_state_digest"] = terminal["state_digest"]
        report["score"] = terminal["state"]["score"]
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def solve_contract(source: Any, *, max_nodes: int = MAX_NODES,
                   max_depth: int = MAX_DEPTH) -> dict[str, Any]:
    spec = normalize_contract_source(source)
    nodes = _limit(max_nodes, "contract search nodes", 1, MAX_NODES)
    depth = _limit(max_depth, "contract search depth", 1, MAX_DEPTH)
    first = new_contract(spec)
    queue: deque[tuple[dict[str, Any], list[dict[str, Any]]]] = deque([(first, [])])
    visited: set[str] = set()
    count = 0
    while queue and count < nodes:
        session, actions = queue.popleft()
        state = session["state"]
        fingerprint = dig({
            "market_state": state["market"]["state"],
            "completed": state["completed"], "score": state["score"],
            "phase": state["phase"], "tick": state["tick"],
        })
        if fingerprint in visited:
            continue
        visited.add(fingerprint)
        count += 1
        if state["phase"] == "won":
            return _result(spec, "found", count, actions)
        if state["phase"] != "active" or len(actions) >= depth:
            continue
        for action in _choices(state["market"]):
            # The node budget is also a hard frontier/memory budget. A
            # saturated queue is inconclusive, never an impossibility proof.
            # Check before allocating another nested replay session.
            if len(queue) >= nodes:
                return _result(spec, "inconclusive", count, None)
            try:
                next_session = _advance(session, action)
            except SceneTravelError:
                continue
            queue.append((next_session, [*actions, action]))
    return _result(spec, "inconclusive", count, None)


def verify_contract_route(source: Any, report: Any) -> dict[str, Any]:
    spec = normalize_contract_source(source)
    _bounded(report)
    if type(report) is not dict or set(report) != {
        "schema_version", "source_digest", "status", "visited_nodes",
        "actions", "terminal_state_digest", "score", "qualification", "checksum",
    }:
        raise SceneTravelError("invalid contract route witness")
    if report["schema_version"] != SCHEMA or report["source_digest"] != dig(spec):
        raise SceneTravelError("contract route source mismatch")
    if report["checksum"] != dig({k: v for k, v in report.items() if k != "checksum"}):
        raise SceneTravelError("contract route checksum mismatch")
    _limit(report["visited_nodes"], "visited nodes", 0, MAX_NODES)
    if report["qualification"] != "offline_replay_witness_only":
        raise SceneTravelError("contract route qualification mismatch")
    if report["status"] == "found":
        if type(report["actions"]) is not list or len(report["actions"]) > MAX_DEPTH:
            raise SceneTravelError("invalid contract route actions")
        terminal = verify_contract(simulate_contract(spec, report["actions"]))
        if (terminal["state"]["phase"] != "won"
                or terminal["state_digest"] != report["terminal_state_digest"]
                or terminal["state"]["score"] != report["score"]):
            raise SceneTravelError("contract route replay mismatch")
    elif report["status"] == "inconclusive":
        if (report["actions"] is not None or report["terminal_state_digest"] is not None
                or report["score"] is not None):
            raise SceneTravelError("inconclusive route claims victory")
    else:
        raise SceneTravelError("unsupported contract route status")
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-contract-route")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--max-nodes", type=int, default=MAX_NODES)
    solve.add_argument("--max-depth", type=int, default=MAX_DEPTH)
    verify = sub.add_parser("verify")
    verify.add_argument("--source-json", required=True)
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_contract()
            result = solve_contract(source)
        elif args.command == "solve":
            result = solve_contract(_json(args.source_json),
                                    max_nodes=args.max_nodes,
                                    max_depth=args.max_depth)
        else:
            result = verify_contract_route(
                _json(args.source_json), _json(args.report_json),
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
