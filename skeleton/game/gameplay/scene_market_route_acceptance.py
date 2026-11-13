"""End-to-end acceptance of a replay-proven offline market route.

This composes the existing canonical market engine, player board, editor,
interactive play, economic conservation, checkpoint replay and portable
packaging. It never grants a route that the actual gameplay reducer rejects.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _bounded, _json, export_market, import_market, new_market,
    original_market, resume_market, verify_market,
)
from skeleton.game.gameplay.scene_market_acceptance import audit_market
from skeleton.game.gameplay.scene_market_board import (
    market_board, verify_market_board,
)
from skeleton.game.gameplay.scene_market_ledger import audit_market_ledger
from skeleton.game.gameplay.scene_market_reconciliation import reconcile_market
from skeleton.game.gameplay.scene_market_route import (
    solve_market_route, verify_market_route,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_route_acceptance.v1"


def accept_market_route(payload: Any, *, max_nodes: int = 4096,
                        max_depth: int = 40,
                        require_victory: bool = True,
                        include_editor: bool = True) -> dict[str, Any]:
    """Qualify one exact authored market and a playable checkpoint continuation."""
    if type(require_victory) is not bool or type(include_editor) is not bool:
        raise SceneTravelError("invalid market route acceptance flags")
    initial = verify_market(payload)
    route = solve_market_route(
        initial, max_nodes=max_nodes, max_depth=max_depth,
    )
    verify_market_route(initial, route)
    board = market_board(
        initial, hint_nodes=max_nodes, hint_depth=max_depth,
    )
    verify_market_board(initial, board)
    if board["hint_report_checksum"] != route["checksum"]:
        raise SceneTravelError("player board and route evidence diverged")
    if route["status"] != "proven_win":
        if require_victory:
            raise SceneTravelError("market route victory not proven within budget")
        report = {
            "schema_version": SCHEMA, "status": "inconclusive",
            "source_digest": initial["source_digest"],
            "initial_state_digest": initial["state_digest"],
            "route_checksum": route["checksum"],
            "board_checksum": board["checksum"],
            "reason": route["reason"], "max_nodes": max_nodes,
            "max_depth": max_depth, "require_victory": require_victory,
            "include_editor": include_editor,
            "qualification": "no_playable_victory_witness",
        }
        report["checksum"] = dig(report)
        _bounded(report)
        return report
    terminal = resume_market(initial, route["actions"])
    if terminal["state"]["phase"] != "won":
        raise SceneTravelError("market route acceptance not terminal victory")
    if import_market(export_market(terminal)) != terminal:
        raise SceneTravelError("market route portable round trip mismatch")
    ledger = audit_market_ledger(terminal)
    transition = reconcile_market(initial, terminal)
    full_actions = [
        event["action"] for event in initial["journal"]
    ] + route["actions"]
    integrated = audit_market(
        initial["source"], full_actions, require_victory=True,
        include_editor=include_editor,
    )
    if (integrated["state_digest"] != terminal["state_digest"]
            or integrated["source_digest"] != initial["source_digest"]
            or integrated["phase"] != terminal["state"]["phase"]
            or integrated["credits"] != ledger["credits_remaining"]
            or integrated["goods"] != ledger["goods_remaining"]
            or integrated["reputation"] != ledger["reputation_earned"]
            or integrated["delivered"] != ledger["delivered"]
            or ledger["state_digest"] != terminal["state_digest"]
            or ledger["journal_length"] != len(full_actions)
            or transition["to_state_digest"] != terminal["state_digest"]
            or transition["actions_applied"] != len(route["actions"])):
        raise SceneTravelError("market integrated acceptance diverged")
    report = {
        "schema_version": SCHEMA, "status": "accepted_offline_witness",
        "source_digest": initial["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "terminal_state_digest": terminal["state_digest"],
        "terminal_save_digest": dig(terminal["save"]),
        "route_checksum": route["checksum"],
        "board_checksum": board["checksum"],
        "ledger_checksum": ledger["checksum"],
        "reconciliation_checksum": transition["checksum"],
        "integrated_acceptance_digest": integrated["report_digest"],
        "portable_checksum": export_market(terminal)["checksum"],
        "actions_from_checkpoint": len(route["actions"]),
        "total_replayed_actions": len(full_actions),
        "reputation": terminal["state"]["reputation"],
        "delivered": terminal["state"]["delivered"],
        "remaining_credits": terminal["state"]["credits"],
        "remaining_goods": terminal["state"]["goods"],
        "max_nodes": max_nodes, "max_depth": max_depth,
        "require_victory": require_victory,
        "include_editor": include_editor,
        "qualification": "one_exact_offline_source_not_device_release",
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def verify_market_route_acceptance(payload: Any,
                                   report: Any) -> dict[str, Any]:
    """Rebuild all evidence, rejecting even a rechecksummed forged report."""
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid market route acceptance report")
    expected = accept_market_route(
        payload, max_nodes=report.get("max_nodes"),
        max_depth=report.get("max_depth"),
        require_victory=report.get("require_victory"),
        include_editor=report.get("include_editor"),
    )
    if expected != report:
        raise SceneTravelError("market route acceptance evidence mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-market-route-accept",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    audit = sub.add_parser("audit")
    verify = sub.add_parser("verify")
    for item in (demo, audit):
        item.add_argument("--max-nodes", type=int, default=4096)
        item.add_argument("--max-depth", type=int, default=40)
        item.add_argument("--allow-inconclusive", action="store_true")
        item.add_argument("--skip-editor", action="store_true")
    audit.add_argument("--session-json", required=True)
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_market()
            result = accept_market_route(
                new_market(source), max_nodes=args.max_nodes,
                max_depth=args.max_depth,
                require_victory=not args.allow_inconclusive,
                include_editor=not args.skip_editor,
            )
        elif args.command == "audit":
            result = accept_market_route(
                _json(args.session_json), max_nodes=args.max_nodes,
                max_depth=args.max_depth,
                require_victory=not args.allow_inconclusive,
                include_editor=not args.skip_editor,
            )
        else:
            result = verify_market_route_acceptance(
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
