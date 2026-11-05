"""Player-facing, source-bound mission hint with replayed next-action preview.

Hints are observational: they cannot alter the campaign, grant rewards or
override a locked ending. Bounded search exhaustion is explicitly inconclusive
and no invented route is returned. The user chooses whether to play a hint.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_mission import (
    MAX_BYTES, MAX_SOURCE_BYTES, _advance, export_mission, import_mission,
    new_mission, original_mission, verify_mission,
)
from skeleton.game.gameplay.scene_mission_interactive import legal_actions
from skeleton.game.gameplay.scene_mission_solver import (
    MAX_DEPTH, MAX_STATES, plan_ending, verify_plan,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id

SCHEMA = "skeleton.scene_mission_assistance.v1"


def _bounded(payload: Any) -> None:
    try:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid mission assistance JSON") from exc
    if len(data) > MAX_BYTES:
        raise SceneTravelError("mission assistance byte budget exceeded")


def _explanation(action: dict[str, Any]) -> str:
    if action["kind"] == "choose":
        return "An authored choice is available at the current scene."
    if action["kind"] == "finish":
        return "The authored ending prerequisites have been earned."
    nested = action["action"]
    if nested["kind"] == "travel":
        return "The canonical scene engine permits this exit."
    if nested["kind"] == "collect":
        return "The canonical scene engine permits this pickup."
    return "The canonical scene engine permits this action."


def assist_mission(source: Any = None, *, session: Any = None,
                   target_ending: str, max_states: int = 256,
                   max_depth: int = 24) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one mission source or checkpoint")
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid assistance state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid assistance depth budget")
    target = _id(target_ending, "target_ending")
    start = new_mission(source) if session is None else verify_mission(session)
    plan = plan_ending(
        session=start, target_ending=target, max_states=max_states,
        max_depth=max_depth,
    )
    action = None
    preview = None
    if plan["status"] == "found":
        verified_final = verify_plan(plan, session=start)
        if verified_final["state"]["ending"] != target:
            raise SceneTravelError("mission assistance route ending mismatch")
        if plan["actions"]:
            action = plan["actions"][0]
            if action not in legal_actions(start):
                raise SceneTravelError("mission assistance proposed illegal move")
            stepped = _advance(start, action)
            bundle = export_mission(stepped)
            if import_mission(bundle) != stepped:
                raise SceneTravelError("mission assistance preview export mismatch")
            preview = {
                "state_digest": stepped["state_digest"],
                "save_digest": dig(stepped["save"]),
                "portable_checksum": bundle["checksum"],
                "scene_id": stepped["state"]["scene"]["state"]["scene_id"],
                "reputation": stepped["state"]["reputation"],
                "missions": list(stepped["state"]["missions"]),
                "ending": stepped["state"]["ending"],
            }
    record = {
        "schema_version": SCHEMA, "status": plan["status"],
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "target_ending": target, "max_states": max_states,
        "max_depth": max_depth, "explored": plan["explored"],
        "budget_exhausted": plan["budget_exhausted"],
        "route_final_digest": plan["final_state_digest"],
        "route_actions": plan["actions"],
        "suggested_action": action,
        "explanation": _explanation(action) if action is not None else (
            "Already at the requested earned ending."
            if plan["status"] == "found" else
            "No safe hint is available within the verified search result."
        ),
        "preview": preview,
        "mutated_session": False,
    }
    record["receipt"] = dig(record)
    _bounded(record)
    return record


def verify_assistance(payload: Any, *, source: Any = None,
                      session: Any = None) -> dict[str, Any]:
    """Recompute the hint, not merely its user-supplied checksum."""
    _bounded(payload)
    required = {
        "schema_version", "status", "source_digest", "initial_state_digest",
        "target_ending", "max_states", "max_depth", "explored",
        "budget_exhausted", "route_final_digest", "route_actions",
        "suggested_action", "explanation", "preview", "mutated_session",
        "receipt",
    }
    if type(payload) is not dict or set(payload) != required:
        raise SceneTravelError("invalid mission assistance receipt")
    expected = assist_mission(
        source, session=session, target_ending=payload["target_ending"],
        max_states=payload["max_states"], max_depth=payload["max_depth"],
    )
    if expected != payload:
        raise SceneTravelError("mission assistance receipt replay mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-assist")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--ending-id", default="lantern_restored")
    parser.add_argument("--max-states", type=int, default=256)
    parser.add_argument("--max-depth", type=int, default=24)
    parser.add_argument("--verify-json")
    args = parser.parse_args(list(argv))
    try:
        source = original_mission() if args.demo else (
            _strict_json(args.source_json, "mission source",
                         max_bytes=MAX_SOURCE_BYTES)
            if args.source_json is not None else None
        )
        saved = (
            _strict_json(args.session_json, "mission checkpoint",
                         max_bytes=MAX_BYTES)
            if args.session_json is not None else None
        )
        if args.verify_json is None:
            result = assist_mission(
                source, session=saved, target_ending=args.ending_id,
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            result = verify_assistance(
                _strict_json(args.verify_json, "assistance receipt",
                             max_bytes=MAX_BYTES),
                source=source, session=saved,
            )
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
