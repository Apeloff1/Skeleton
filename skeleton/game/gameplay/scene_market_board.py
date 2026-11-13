"""Player-facing market order board and deterministic non-mutating hints.

The board is derived from a verified checkpoint, never a second inventory or
currency authority. The optional route hint is a replay-proven action witness.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _bounded, _json, new_market, original_market, verify_market,
)
from skeleton.game.gameplay.scene_market_route import (
    _choices, solve_market_route, verify_market_route,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_board.v1"


def market_board(payload: Any, *, hint_nodes: int = 256,
                 hint_depth: int = 24) -> dict[str, Any]:
    session = verify_market(payload)
    state, source = session["state"], session["source"]
    tile = state["tile"]["state"]
    current = tile["scene"]["state"]["scene_id"]
    remaining = [
        {"delivery_id": item["delivery_id"],
         "goods": item["goods"], "reputation": item["reputation"],
         "scene_id": item["scene_id"], "at": item["at"]}
        for item in source["deliveries"]
        if item["delivery_id"] not in state["delivered"]
    ]
    inventory = dict(sorted(state["goods"].items()))
    route = solve_market_route(
        session, max_nodes=hint_nodes, max_depth=hint_depth,
    )
    result = {
        "schema_version": SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "save_digest": dig(session["save"]),
        "phase": state["phase"], "tick": state["tick"],
        "scene_id": current, "position": tile["position"],
        "credits": state["credits"], "goods": inventory,
        "reputation": state["reputation"],
        "completed_deliveries": state["delivered"],
        "remaining_deliveries": remaining,
        "required_remaining": sorted(
            set(source["required_deliveries"]) - set(state["delivered"])
        ),
        "legal_action_candidates": (
            _choices(session) if state["phase"] == "active" else []
        ),
        "hint_status": route["status"],
        "hint_reason": route["reason"],
        "hint_action": (
            route["actions"][0] if route["actions"] else None
        ),
        "hint_report_checksum": route["checksum"],
        "hint_node_budget": hint_nodes,
        "hint_depth_budget": hint_depth,
        "qualification": "source_bound_offline_hint_not_omniscience",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def verify_market_board(payload: Any, report: Any) -> dict[str, Any]:
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid market board")
    expected = market_board(
        payload, hint_nodes=report.get("hint_node_budget"),
        hint_depth=report.get("hint_depth_budget"),
    )
    if report != expected:
        raise SceneTravelError("market board replay mismatch")
    session = verify_market(payload)
    route = solve_market_route(
        session, max_nodes=report["hint_node_budget"],
        max_depth=report["hint_depth_budget"],
    )
    verify_market_route(session, route)
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-board")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    inspect = sub.add_parser("inspect")
    verify = sub.add_parser("verify")
    for item in (demo, inspect):
        item.add_argument("--hint-nodes", type=int, default=256)
        item.add_argument("--hint-depth", type=int, default=24)
    inspect.add_argument("--session-json", required=True)
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--board-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_market()
            result = market_board(
                new_market(source), hint_nodes=args.hint_nodes,
                hint_depth=args.hint_depth,
            )
        elif args.command == "inspect":
            result = market_board(
                _json(args.session_json), hint_nodes=args.hint_nodes,
                hint_depth=args.hint_depth,
            )
        else:
            result = verify_market_board(
                _json(args.session_json), _json(args.board_json),
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
