"""Bounded, fail-closed evacuation route search with canonical replay witnesses."""
from __future__ import annotations

import argparse
import heapq
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_evacuation import (
    MAX_BYTES, _advance, _bounded, demo_actions, export_evacuation,
    new_evacuation, normalize_evacuation, original_evacuation,
    simulate_evacuation, verify_evacuation,
)
from skeleton.game.gameplay.scene_evacuation_board import legal_evacuation_actions
from skeleton.game.gameplay.scene_travel import SceneTravelError

MAX_SEARCH_NODES = 4096
MAX_SEARCH_DEPTH = 32


def _witness(source: Any, actions: list[dict[str, Any]]) -> dict[str, Any]:
    saved = simulate_evacuation(source, actions)
    if saved["state"]["phase"] != "evacuated":
        raise SceneTravelError("evacuation witness does not reach earned victory")
    bundle = export_evacuation(saved)
    result = {
        "schema_version": "skeleton.scene_evacuation_route.v1",
        "status": "found", "source_digest": saved["source_digest"],
        "state_digest": saved["state_digest"],
        "actions": actions, "reward": saved["state"]["reward"],
        "portable_checksum": bundle["checksum"],
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def solve_evacuation(source: Any, *, max_nodes: int = MAX_SEARCH_NODES,
                     max_depth: int = MAX_SEARCH_DEPTH,
                     hint_actions: Any = None) -> dict[str, Any]:
    spec = normalize_evacuation(source)
    if (type(max_nodes) is not int or not 1 <= max_nodes <= MAX_SEARCH_NODES
            or type(max_depth) is not int or not 1 <= max_depth <= MAX_SEARCH_DEPTH):
        raise SceneTravelError("evacuation search budget outside bounds")
    if hint_actions is not None:
        if type(hint_actions) is not list or len(hint_actions) > max_depth:
            raise SceneTravelError("invalid evacuation search hint")
        try:
            return _witness(spec, hint_actions)
        except SceneTravelError:
            pass  # A hint is never accepted without canonical replay.
    initial = new_evacuation(spec)
    counter = 0
    heap: list[tuple[int, int, list[dict[str, Any]], dict[str, Any]]] = [
        (0, counter, [], initial),
    ]
    seen = {initial["state_digest"]}
    expanded = 0
    generated = 1
    while heap and expanded < max_nodes:
        _, _, actions, current = heapq.heappop(heap)
        expanded += 1
        if len(actions) >= max_depth:
            continue
        for action in legal_evacuation_actions(current):
            next_session = _advance(current, action)
            next_actions = [*actions, action]
            if next_session["state"]["phase"] == "evacuated":
                return _witness(spec, next_actions)
            if next_session["state"]["phase"] != "active":
                continue
            key = next_session["state_digest"]
            if key in seen or generated >= max_nodes:
                continue
            seen.add(key)
            generated += 1
            counter += 1
            state = next_session["state"]
            remaining = max(0, spec["required_rescues"] - len(state["passengers"]))
            unfinished = 0 if state["mission"]["state"]["phase"] == "finished" else 1
            # Deterministic preference for rescues and earned mission progress;
            # never claims shortest-path optimality under this heuristic.
            score = remaining * 100 + unfinished * 20
            score -= len(state["mission"]["state"]["missions"]) * 5
            score += state["tick"]
            heapq.heappush(heap, (score, counter, next_actions, next_session))
    result = {
        "schema_version": "skeleton.scene_evacuation_route.v1",
        "status": "inconclusive", "source_digest": dig(spec),
        "expanded": expanded, "generated": generated,
        "max_nodes": max_nodes, "max_depth": max_depth,
        "reason": "bounded search exhausted without a verified winning route",
    }
    result["receipt"] = dig(result)
    return result


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-evacuation-solve")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    solve = sub.add_parser("solve")
    solve.add_argument("--source-json", required=True)
    solve.add_argument("--hint-json")
    solve.add_argument("--max-nodes", type=int, default=MAX_SEARCH_NODES)
    solve.add_argument("--max-depth", type=int, default=MAX_SEARCH_DEPTH)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = solve_evacuation(original_evacuation(),
                                      hint_actions=demo_actions())
        else:
            parse = lambda raw: _strict_json(raw, "evacuation route", max_bytes=MAX_BYTES)
            result = solve_evacuation(
                parse(args.source_json), max_nodes=args.max_nodes,
                max_depth=args.max_depth,
                hint_actions=(parse(args.hint_json)
                              if args.hint_json is not None else None),
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
