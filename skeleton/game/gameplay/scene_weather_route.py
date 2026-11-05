"""Bounded canonical weather routing; never assert impossibility from exhaustion."""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_survival_route import legal_survival_actions
from skeleton.game.gameplay.scene_tile_walk import _bounded, _json
from skeleton.game.gameplay.scene_travel import SceneTravelError
from skeleton.game.gameplay.scene_weather import (
    _advance, export_weather, import_weather, new_weather, original_weather,
    resume_weather, verify_weather,
)

SCHEMA = "skeleton.scene_weather_route.v1"
MAX_STATES = 1024
MAX_DEPTH = 48


def _limits(max_states: int, max_depth: int) -> None:
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid weather route state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid weather route depth budget")


def legal_weather_actions(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Candidate actions only; the canonical reducer is final authority."""
    current = verify_weather(session)
    state = current["state"]
    if state["phase"] != "active":
        return []
    candidates = [
        {"kind": "survival", "action": action}
        for action in legal_survival_actions(state["survival"])
    ]
    for ident in state["owned_gear"]:
        if ident != state["equipped"]:
            candidates.append({"kind": "equip", "gear_id": ident})
    if state["equipped"] is not None:
        candidates.append({"kind": "unequip"})
    accepted = []
    for action in sorted(candidates, key=lambda a: json.dumps(a, sort_keys=True)):
        try:
            _advance(current, action)
        except SceneTravelError:
            continue
        accepted.append(action)
    return accepted


def _receipt(start: dict[str, Any], terminal: dict[str, Any] | None,
             actions: list[dict[str, Any]], explored: int,
             max_states: int, max_depth: int, reason: str) -> dict[str, Any]:
    found = terminal is not None and terminal["state"]["phase"] == "won"
    bundle = export_weather(terminal) if found else None
    result = {
        "schema_version": SCHEMA,
        "status": "proven_win" if found else "inconclusive",
        "reason": "canonical_replay_win" if found else reason,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "initial_save_digest": dig(start["save"]),
        "final_state_digest": terminal["state_digest"] if found else None,
        "portable_checksum": bundle["checksum"] if bundle else None,
        "actions": actions if found else [],
        "explored_states": explored,
        "max_states": max_states, "max_depth": max_depth,
        "proof_kind": "replay_witness_not_signature",
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def solve_weather_route(source: Any = None, *, session: Any = None,
                        max_states: int = 512,
                        max_depth: int = 24) -> dict[str, Any]:
    """Breadth-first legal routes with explicit finite resource budgets.

    Weather depends on the action tick, so pruning by position alone is unsound.
    State digests preserve tick, gear, food, damage, stamina and scene choices.
    Search exhaustion is always inconclusive, never an impossibility proof.
    """
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one weather source or checkpoint")
    _limits(max_states, max_depth)
    start = new_weather(source) if session is None else verify_weather(session)
    if start["state"]["phase"] == "won":
        return _receipt(start, start, [], 0, max_states, max_depth, "already_won")
    if start["state"]["phase"] != "active":
        return _receipt(start, None, [], 0, max_states, max_depth, "terminal_not_won")
    queue = deque([(start, ())])
    seen = {start["state_digest"]}
    explored = 0
    while queue:
        if explored >= max_states:
            return _receipt(start, None, [], explored, max_states, max_depth,
                            "state_budget_exhausted")
        current, path = queue.popleft()
        explored += 1
        if len(path) >= max_depth:
            continue
        for action in legal_weather_actions(current):
            following = _advance(current, action)
            next_path = (*path, action)
            if following["state"]["phase"] == "won":
                final = resume_weather(start, list(next_path))
                if final != following or import_weather(export_weather(final)) != final:
                    raise SceneTravelError("weather route portable replay mismatch")
                return _receipt(start, final, list(next_path), explored,
                                max_states, max_depth, "canonical_replay_win")
            if following["state"]["phase"] != "active":
                continue
            key = following["state_digest"]
            if key not in seen:
                seen.add(key)
                queue.append((following, next_path))
    return _receipt(start, None, [], explored, max_states, max_depth,
                    "depth_or_search_exhausted")


def verify_weather_route(proof: Any, *, source: Any = None,
                         session: Any = None) -> dict[str, Any]:
    """Recompute the exact search and independently replay the winning path."""
    _bounded(proof)
    if type(proof) is not dict or set(proof) != {
        "schema_version", "status", "reason", "source_digest",
        "initial_state_digest", "initial_save_digest", "final_state_digest",
        "portable_checksum", "actions", "explored_states", "max_states",
        "max_depth", "proof_kind", "checksum",
    } or proof["schema_version"] != SCHEMA or proof["status"] != "proven_win":
        raise SceneTravelError("invalid or non-winning weather route witness")
    _limits(proof["max_states"], proof["max_depth"])
    if proof["checksum"] != dig({k: v for k, v in proof.items() if k != "checksum"}):
        raise SceneTravelError("weather route checksum mismatch")
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one weather source or checkpoint")
    start = new_weather(source) if session is None else verify_weather(session)
    expected = solve_weather_route(session=start, max_states=proof["max_states"],
                                   max_depth=proof["max_depth"])
    if expected != proof:
        raise SceneTravelError("weather route source or search witness mismatch")
    final = resume_weather(start, proof["actions"])
    if (final["state"]["phase"] != "won"
            or final["state_digest"] != proof["final_state_digest"]
            or import_weather(export_weather(final)) != final
            or export_weather(final)["checksum"] != proof["portable_checksum"]):
        raise SceneTravelError("weather route terminal replay mismatch")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-route")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("solve", "verify"):
        p = sub.add_parser(command)
        source_group = p.add_mutually_exclusive_group(required=True)
        source_group.add_argument("--source-json")
        source_group.add_argument("--session-json")
        if command == "solve":
            p.add_argument("--max-states", type=int, default=512)
            p.add_argument("--max-depth", type=int, default=24)
        else:
            p.add_argument("--proof-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_weather()
            result = solve_weather_route(source, max_states=256, max_depth=16)
        else:
            options = ({"source": _json(args.source_json)}
                       if args.source_json is not None else
                       {"session": _json(args.session_json)})
            if args.command == "solve":
                result = solve_weather_route(**options, max_states=args.max_states,
                                             max_depth=args.max_depth)
            else:
                final = verify_weather_route(_json(args.proof_json), **options)
                result = {"ok": True, "phase": final["state"]["phase"],
                          "state_digest": final["state_digest"],
                          "portable_checksum": export_weather(final)["checksum"]}
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
