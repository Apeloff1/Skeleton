"""Bounded survival route solver with canonical replay and portable proof.

Search exhaustion is inconclusive; it is never an impossibility certificate.
The solver only emits actions accepted by the real tile survival runtime.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.scene_tile_route import legal_tile_actions
from skeleton.game.gameplay.scene_tile_survival import (
    SCHEMA as SURVIVAL_SCHEMA, _advance, _json, export_survival,
    import_survival, new_survival, original_survival, resume_survival,
    verify_survival,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_tile_survival_route.v1"
MAX_STATES = 4096
MAX_DEPTH = 64


def _limits(max_states: int, max_depth: int) -> None:
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid survival route state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid survival route depth budget")


def legal_survival_actions(session: Any) -> list[dict[str, Any]]:
    current = verify_survival(session)
    state = current["state"]
    if state["phase"] != "active" or state["tick"] >= current["source"]["turn_limit"]:
        return []
    actions = [
        {"kind": "tile", "action": action}
        for action in legal_tile_actions(state["tile"])
    ]
    tile_state = state["tile"]["state"]
    scene_id = tile_state["scene"]["state"]["scene_id"]
    position = tile_state["position"]
    camp_id = scene_id + ":" + str(position[0]) + ":" + str(position[1])
    if (state["food"] > 0
            and state["health"] < current["source"]["max_health"]
            and camp_id not in state["used_camps"]
            and any(c["scene_id"] == scene_id and c["at"] == position
                    for c in current["source"]["camps"])):
        actions.append({"kind": "rest"})
    return sorted(actions, key=lambda a: json.dumps(a, sort_keys=True))


def _signature(session: dict[str, Any]) -> str:
    state = session["state"]
    tile = state["tile"]["state"]
    scene = tile["scene"]["state"]
    # Shorter paths dominate longer paths with identical gameplay resources.
    # Do not include journal digests, ticks or visited-scene presentation.
    return json.dumps({
        "scene_id": scene["scene_id"], "position": tile["position"],
        "inventory": scene["inventory"], "collected": scene["collected"],
        "scene_phase": scene["phase"], "phase": state["phase"],
        "health": state["health"], "food": state["food"],
        "used_camps": state["used_camps"],
    }, sort_keys=True, separators=(",", ":"))


def _result(start: dict[str, Any], target: str, status: str,
            actions: list[dict[str, Any]], explored: int, truncated: bool,
            final: dict[str, Any] | None,
            max_states: int, max_depth: int) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "target_phase": target, "status": status, "actions": actions,
        "explored": explored, "budget_exhausted": truncated,
        "max_states": max_states, "max_depth": max_depth,
        "final_state_digest": final["state_digest"] if final is not None else None,
        "portable_checksum": (
            export_survival(final)["checksum"] if final is not None else None
        ),
    }


def solve_survival(source: Any = None, *, session: Any = None,
                   target_phase: str = "won", max_states: int = 2048,
                   max_depth: int = 32) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one survival source or checkpoint")
    _limits(max_states, max_depth)
    if type(target_phase) is not str or target_phase not in (
        "won", "lost", "draw",
    ):
        raise SceneTravelError("invalid survival target phase")
    start = new_survival(source) if session is None else verify_survival(session)
    if start["state"]["phase"] != "active":
        matched = start["state"]["phase"] == target_phase
        return _result(
            start, target_phase, "found" if matched else "unreachable",
            [], 0, False, start if matched else None, max_states, max_depth,
        )
    queue = deque([(start, ())])
    seen = {_signature(start)}
    explored = 0
    truncated = False
    while queue:
        if explored >= max_states:
            truncated = True
            break
        current, path = queue.popleft()
        explored += 1
        if len(path) >= max_depth:
            if legal_survival_actions(current):
                truncated = True
            continue
        for action in legal_survival_actions(current):
            try:
                following = _advance(current, action)
            except SceneTravelError:
                continue
            witness = (*path, action)
            if following["state"]["phase"] == target_phase:
                portable = export_survival(following)
                if import_survival(portable) != following:
                    raise SceneTravelError("survival portable witness mismatch")
                return _result(
                    start, target_phase, "found", list(witness), explored,
                    False, following, max_states, max_depth,
                )
            if following["state"]["phase"] != "active":
                continue
            signature = _signature(following)
            if signature not in seen:
                seen.add(signature)
                queue.append((following, witness))
    return _result(
        start, target_phase,
        "inconclusive" if truncated else "unreachable",
        [], explored, truncated, None, max_states, max_depth,
    )


def verify_plan(payload: Any, *, source: Any = None,
                session: Any = None) -> dict[str, Any]:
    if type(payload) is not dict or set(payload) != {
        "schema_version", "source_digest", "initial_state_digest",
        "target_phase", "status", "actions", "explored",
        "budget_exhausted", "max_states", "max_depth",
        "final_state_digest", "portable_checksum",
    } or payload["schema_version"] != SCHEMA or payload["status"] != "found":
        raise SceneTravelError("invalid or non-playable survival route witness")
    _limits(payload["max_states"], payload["max_depth"])
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one survival source or checkpoint")
    start = new_survival(source) if session is None else verify_survival(session)
    expected = solve_survival(
        session=start, target_phase=payload["target_phase"],
        max_states=payload["max_states"], max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise SceneTravelError("survival route search receipt mismatch")
    final = resume_survival(start, payload["actions"])
    if (final["state"]["phase"] != payload["target_phase"]
            or final["state_digest"] != payload["final_state_digest"]
            or export_survival(final)["checksum"] != payload["portable_checksum"]):
        raise SceneTravelError("survival route replay mismatch")
    return final


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-survival-route")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for command in ("solve", "verify"):
        p = sub.add_parser(command)
        source = p.add_mutually_exclusive_group(required=True)
        source.add_argument("--source-json")
        source.add_argument("--session-json")
        if command == "solve":
            p.add_argument("--target", choices=("won", "lost", "draw"),
                           default="won")
            p.add_argument("--max-states", type=int, default=2048)
            p.add_argument("--max-depth", type=int, default=32)
        else:
            p.add_argument("--plan-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, _ = original_survival()
            result = solve_survival(source)
        else:
            options = (
                {"source": _json(args.source_json)}
                if args.source_json is not None
                else {"session": _json(args.session_json)}
            )
            if args.command == "solve":
                result = solve_survival(
                    **options, target_phase=args.target,
                    max_states=args.max_states, max_depth=args.max_depth,
                )
            else:
                final = verify_plan(_json(args.plan_json), **options)
                result = {
                    "ok": True, "state_digest": final["state_digest"],
                    "phase": final["state"]["phase"],
                    "portable_checksum": export_survival(final)["checksum"],
                }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, TypeError, ValueError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
