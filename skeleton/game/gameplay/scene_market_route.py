"""Bounded, replay-proven market route search over the canonical tile/economy reducer.

A route is a witness only after every action has been replayed by the actual
market engine. An unsuccessful bounded search is *inconclusive*, never a claim
that the authored game cannot be won.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_market import (
    _advance, _at, _bounded, _json, new_market, original_market,
    resume_market, verify_market,
)
from skeleton.game.gameplay.scene_tile_walk import DIRECTIONS, MAX_STEPS
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_market_route.v1"
MAX_NODES = 4096
MAX_DEPTH = 64


def _choices(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate candidate commands from authored positions, not free goods."""
    state, source = session["state"], session["source"]
    tile = state["tile"]["state"]
    scene_id = tile["scene"]["state"]["scene_id"]
    pos = tile["position"]
    area = next(area for area in source["tile_source"]["maps"]
                if area["scene_id"] == scene_id)
    result: list[dict[str, Any]] = []
    for delivery in source["deliveries"]:
        if (_at(state["tile"], delivery)
                and delivery["delivery_id"] not in state["delivered"]
                and all(state["goods"].get(item, 0) >= quantity
                        for item, quantity in delivery["goods"].items())):
            result.append({"kind": "deliver", "delivery_id": delivery["delivery_id"]})
    for recipe in source["recipes"]:
        if (_at(state["tile"], recipe)
                and all(state["goods"].get(item, 0) >= quantity
                        for item, quantity in recipe["inputs"].items())):
            result.append({"kind": "craft", "recipe_id": recipe["recipe_id"]})
    for market in source["markets"]:
        if not _at(state["tile"], market):
            continue
        for offer in market["offers"]:
            if (state["credits"] >= offer["price"]
                    and state["purchases"].get(offer["offer_id"], 0)
                    < offer["stock"]):
                result.append({"kind": "buy", "offer_id": offer["offer_id"]})
    for pickup in area["pickups"]:
        if pickup["at"] == pos:
            result.append({"kind": "tile", "action": {
                "kind": "collect", "pickup_id": pickup["id"],
            }})
    for exit_ in area["exits"]:
        if exit_["at"] == pos:
            result.append({"kind": "tile", "action": {
                "kind": "travel", "exit_id": exit_["id"],
            }})
    for direction, (dx, dy) in DIRECTIONS.items():
        target = [pos[0] + dx, pos[1] + dy]
        if (0 <= target[0] < area["width"]
                and 0 <= target[1] < area["height"]
                and target not in area["walls"]):
            result.append({"kind": "tile", "action": {
                "kind": "move", "direction": direction,
            }})
    return result


def _fingerprint(session: dict[str, Any]) -> str:
    """Ignore only monotone counters; retain all consequential world state.

    This is a search heuristic, not a proof of impossibility. Therefore a
    search without a winning witness always returns inconclusive.
    """
    state = session["state"]
    tile = state["tile"]["state"]
    scene = copy.deepcopy(tile["scene"]["state"])
    scene.pop("tick", None)
    return dig({
        "scene": scene, "position": tile["position"],
        "phase": state["phase"], "credits": state["credits"],
        "goods": state["goods"], "purchases": state["purchases"],
        "delivered": state["delivered"], "reputation": state["reputation"],
    })


def _report(initial: dict[str, Any], terminal: dict[str, Any] | None,
            actions: list[dict[str, Any]], explored: int, budget: int,
            depth: int, reason: str) -> dict[str, Any]:
    won = terminal is not None and terminal["state"]["phase"] == "won"
    result = {
        "schema_version": SCHEMA,
        "status": "proven_win" if won else "inconclusive",
        "reason": "canonical_replay_victory" if won else reason,
        "source_digest": initial["source_digest"],
        "initial_state_digest": initial["state_digest"],
        "initial_save_digest": dig(initial["save"]),
        "terminal_state_digest": terminal["state_digest"] if won else None,
        "terminal_save_digest": dig(terminal["save"]) if won else None,
        "actions": actions if won else [],
        "action_count": len(actions) if won else 0,
        "explored_states": explored, "node_budget": budget,
        "depth_budget": depth,
        "proof_kind": "canonical_replay_not_authentication",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def solve_market_route(payload: Any, *, max_nodes: int = 1024,
                       max_depth: int = 32) -> dict[str, Any]:
    """Search a real checkpoint; never invent purchases, exits or rewards."""
    if type(max_nodes) is not int or not 1 <= max_nodes <= MAX_NODES:
        raise SceneTravelError("invalid market route node budget")
    if type(max_depth) is not int or not 0 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid market route depth budget")
    initial = verify_market(payload)
    if initial["state"]["phase"] == "won":
        return _report(initial, initial, [], 1, max_nodes, max_depth, "")
    if initial["state"]["phase"] != "active":
        return _report(initial, None, [], 1, max_nodes, max_depth,
                       "terminal_checkpoint")
    frontier = deque([(initial, [])])
    seen = {_fingerprint(initial)}
    explored = 0
    truncated_depth = False
    while frontier:
        if explored >= max_nodes:
            return _report(initial, None, [], explored, max_nodes, max_depth,
                           "node_budget_exhausted")
        session, actions = frontier.popleft()
        explored += 1
        if len(actions) >= max_depth or session["state"]["tick"] >= MAX_STEPS:
            truncated_depth = True
            continue
        for action in _choices(session):
            try:
                successor = _advance(session, action)
            except SceneTravelError:
                continue
            path = [*actions, action]
            if successor["state"]["phase"] == "won":
                # Re-run from the exact initial checkpoint, not the BFS object.
                replay = resume_market(initial, path)
                if (replay != successor or replay["state"]["phase"] != "won"):
                    raise SceneTravelError("market route replay mismatch")
                return _report(initial, replay, path, explored, max_nodes,
                               max_depth, "")
            if successor["state"]["phase"] != "active":
                continue
            identity = _fingerprint(successor)
            if identity not in seen:
                seen.add(identity)
                frontier.append((successor, path))
    return _report(initial, None, [], explored, max_nodes, max_depth,
                   "depth_budget_exhausted" if truncated_depth
                   else "no_winning_witness_in_bounded_search")


def verify_market_route(payload: Any, report: Any) -> dict[str, Any]:
    """Recompute search and exact witness; reject recomputed fake checksums."""
    _bounded(report)
    if type(report) is not dict:
        raise SceneTravelError("invalid market route report")
    nodes = report.get("node_budget")
    depth = report.get("depth_budget")
    expected = solve_market_route(payload, max_nodes=nodes, max_depth=depth)
    if expected != report:
        raise SceneTravelError("market route report does not match canonical search")
    if report["status"] == "proven_win":
        session = verify_market(payload)
        replay = resume_market(session, report["actions"])
        if (replay["state_digest"] != report["terminal_state_digest"]
                or dig(replay["save"]) != report["terminal_save_digest"]
                or replay["state"]["phase"] != "won"):
            raise SceneTravelError("market route witness replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-market-route")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    solve = sub.add_parser("solve")
    verify = sub.add_parser("verify")
    for item in (demo, solve):
        item.add_argument("--max-nodes", type=int, default=1024)
        item.add_argument("--max-depth", type=int, default=32)
    solve.add_argument("--session-json", required=True)
    verify.add_argument("--session-json", required=True)
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_market()
            result = solve_market_route(
                new_market(source), max_nodes=args.max_nodes,
                max_depth=args.max_depth,
            )
        elif args.command == "solve":
            result = solve_market_route(
                _json(args.session_json), max_nodes=args.max_nodes,
                max_depth=args.max_depth,
            )
        else:
            result = verify_market_route(
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
