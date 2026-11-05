"""Read-only mission objectives and legal-action board with replay custody.

All mission, reputation and movement data comes from the canonical director.
The board is a view, never an alternate state machine or a reward source.
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
    MAX_BYTES, MAX_SOURCE_BYTES, _satisfied, new_mission, original_mission,
    verify_mission,
)
from skeleton.game.gameplay.scene_mission_interactive import legal_actions
from skeleton.game.gameplay.scene_travel import SceneTravelError, _object

SCHEMA = "skeleton.scene_mission_board.v1"
BUNDLE = "skeleton.scene_mission_board_bundle.v1"


def _bounded(value: Any) -> None:
    try:
        data = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid mission board JSON") from exc
    if len(data) > MAX_BYTES:
        raise SceneTravelError("mission board byte budget exceeded")


def inspect_board(payload: Any) -> dict[str, Any]:
    """Derive objective prerequisites, earned progress and playable actions."""
    session = verify_mission(payload)
    state = session["state"]
    scene = state["scene"]["state"]
    earned = set(state["missions"])
    objectives = []
    for mission in session["source"]["missions"]:
        missing = [dep for dep in mission["requires"] if dep not in earned]
        status = (
            "earned" if mission["id"] in earned else
            "blocked" if missing else
            "trigger_ready" if _satisfied(mission, state) else
            "available"
        )
        objectives.append({
            "id": mission["id"], "status": status,
            "missing_dependencies": missing,
            "trigger": mission["trigger"],
            "reputation_reward": mission["reputation"],
        })
    report = {
        "schema_version": SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "save_digest": dig(session["save"]),
        "tick": state["tick"], "phase": state["phase"],
        "ending": state["ending"], "scene_id": scene["scene_id"],
        "scene_phase": scene["phase"],
        "inventory": list(scene["inventory"]),
        "visited": list(scene["visited"]),
        "collected": list(scene["collected"]),
        "choices": dict(sorted(state["choices"].items())),
        "missions_earned": list(state["missions"]),
        "reputation": state["reputation"],
        "objectives": objectives,
        "available_actions": legal_actions(session),
    }
    report["receipt"] = dig(report)
    _bounded(report)
    return report


def verify_board(report: Any, *, session: Any) -> dict[str, Any]:
    """Recompute all hints, rejecting forged data even with a valid checksum."""
    _bounded(report)
    expected = inspect_board(session)
    if type(report) is not dict or report != expected:
        raise SceneTravelError("mission board replay mismatch")
    return expected


def export_board(payload: Any) -> dict[str, Any]:
    session = verify_mission(payload)
    report = inspect_board(session)
    record = {
        "schema_version": BUNDLE,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session, "board": report,
    }
    bundle = {**record, "checksum": dig(record)}
    _bounded(bundle)
    return bundle


def import_board(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest",
        "session", "board", "checksum",
    }, "mission board bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported mission board bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("mission board checksum mismatch")
    session = verify_mission(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise SceneTravelError("mission board source/state mismatch")
    return verify_board(obj["board"], session=session)


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-board")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    group.add_argument("--bundle-json")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args(list(argv))
    try:
        if args.bundle_json is not None:
            if args.export:
                raise SceneTravelError("cannot re-export a board bundle")
            result = import_board(_strict_json(args.bundle_json, "board bundle", max_bytes=MAX_BYTES))
        else:
            session = (
                verify_mission(_strict_json(args.session_json, "mission save", max_bytes=MAX_BYTES))
                if args.session_json is not None else
                new_mission(original_mission() if args.demo else
                            _strict_json(args.source_json, "mission source", max_bytes=MAX_SOURCE_BYTES))
            )
            result = export_board(session) if args.export else inspect_board(session)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
