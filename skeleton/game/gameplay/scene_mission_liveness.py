"""Bounded playable mission liveness and softlock witness inspection.

Unlike ending-route searches, this audit explores every admitted canonical
action until its explicit budget, recording reachable active states with no
legal continuation. Every finding includes replayable actions and a portable
save. An incomplete exploration is never reported as a clean world.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_mission import (
    MAX_BYTES, MAX_SOURCE_BYTES, _advance, export_mission, import_mission,
    new_mission, original_mission, resume_mission, verify_mission,
)
from skeleton.game.gameplay.scene_mission_solver import (
    MAX_DEPTH, MAX_STATES, _key, _options,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError

SCHEMA = "skeleton.scene_mission_liveness.v1"
MAX_FINDINGS = 16


def _limits(max_states: int, max_depth: int, max_findings: int) -> None:
    if type(max_states) is not int or not 1 <= max_states <= MAX_STATES:
        raise SceneTravelError("invalid liveness state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= MAX_DEPTH:
        raise SceneTravelError("invalid liveness depth budget")
    if type(max_findings) is not int or not 1 <= max_findings <= MAX_FINDINGS:
        raise SceneTravelError("invalid liveness finding budget")


def _bounded(payload: Any) -> None:
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid liveness JSON") from exc
    if len(raw) > MAX_BYTES:
        raise SceneTravelError("liveness report exceeds byte budget")


def _witness(snapshot: dict[str, Any],
             actions: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    saved = export_mission(snapshot)
    if import_mission(saved) != snapshot:
        raise SceneTravelError("liveness checkpoint portable mismatch")
    state = snapshot["state"]
    return {
        "actions": list(actions),
        "state_digest": snapshot["state_digest"],
        "save_digest": dig(snapshot["save"]),
        "portable_checksum": saved["checksum"],
        "scene_id": state["scene"]["state"]["scene_id"],
        "scene_phase": state["scene"]["state"]["phase"],
        "reputation": state["reputation"],
        "missions": list(state["missions"]),
        "choices": dict(sorted(state["choices"].items())),
        "reason": "no_canonical_legal_action",
        "safe_fallback": "restore_previous_verified_checkpoint_or_edit_source",
    }


def audit_liveness(source: Any = None, *, session: Any = None,
                   max_states: int = 256, max_depth: int = 24,
                   max_findings: int = 8) -> dict[str, Any]:
    """Explore legal gameplay without inventing missing quests or rewards."""
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one mission source or checkpoint")
    _limits(max_states, max_depth, max_findings)
    start = new_mission(source) if session is None else verify_mission(session)
    queue = deque([(start, ())])
    seen = {_key(start["state"])}
    explored = 0
    truncated = False
    softlocks: list[dict[str, Any]] = []
    endings: dict[str, dict[str, Any]] = {}
    while queue:
        if explored >= max_states:
            truncated = True
            break
        current, actions = queue.popleft()
        explored += 1
        state = current["state"]
        if state["phase"] == "finished":
            ending = state["ending"]
            if ending not in endings:
                bundle = export_mission(current)
                if import_mission(bundle) != current:
                    raise SceneTravelError("liveness ending portable mismatch")
                endings[ending] = {
                    "ending_id": ending, "actions": list(actions),
                    "state_digest": current["state_digest"],
                    "portable_checksum": bundle["checksum"],
                }
            continue
        legal: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for action in _options(current):
            try:
                successor = _advance(current, action)
            except SceneTravelError:
                continue
            legal.append((action, successor))
        if not legal:
            if len(softlocks) >= max_findings:
                truncated = True
                break
            softlocks.append(_witness(current, actions))
            continue
        if len(actions) >= max_depth:
            truncated = True
            continue
        for action, successor in legal:
            key = _key(successor["state"])
            if key in seen:
                continue
            seen.add(key)
            queue.append((successor, (*actions, action)))
            # Prevent the frontier from growing without a strict memory cap.
            if len(seen) > max_states * 4:
                truncated = True
                break
        if truncated and len(seen) > max_states * 4:
            break
    report = {
        "schema_version": SCHEMA,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "max_states": max_states, "max_depth": max_depth,
        "max_findings": max_findings,
        "states_explored": explored, "unique_states": len(seen),
        "complete": not truncated, "budget_exhausted": truncated,
        "status": (
            "softlock_found" if softlocks else
            "inconclusive" if truncated else "no_softlock"
        ),
        "softlocks": softlocks,
        "reachable_endings": [endings[key] for key in sorted(endings)],
    }
    report["checksum"] = dig(report)
    _bounded(report)
    return report


def verify_liveness(payload: Any, *, source: Any = None,
                    session: Any = None) -> dict[str, Any]:
    """Recompute bounded search and replay each claimed softlock checkpoint."""
    _bounded(payload)
    keys = {
        "schema_version", "source_digest", "initial_state_digest",
        "max_states", "max_depth", "max_findings", "states_explored",
        "unique_states", "complete", "budget_exhausted", "status",
        "softlocks", "reachable_endings", "checksum",
    }
    if type(payload) is not dict or set(payload) != keys:
        raise SceneTravelError("invalid liveness receipt")
    if (source is None) == (session is None):
        raise SceneTravelError("supply exactly one mission source or checkpoint")
    _limits(payload["max_states"], payload["max_depth"], payload["max_findings"])
    start = new_mission(source) if session is None else verify_mission(session)
    expected = audit_liveness(
        session=start, max_states=payload["max_states"],
        max_depth=payload["max_depth"], max_findings=payload["max_findings"],
    )
    if payload != expected:
        raise SceneTravelError("liveness search receipt replay mismatch")
    for witness in expected["softlocks"]:
        snapshot = resume_mission(start, witness["actions"])
        if snapshot["state"]["phase"] != "active":
            raise SceneTravelError("liveness witness is not active")
        if any(
            _is_legal(snapshot, action) for action in _options(snapshot)
        ):
            raise SceneTravelError("liveness witness still has legal actions")
        if _witness(snapshot, tuple(witness["actions"])) != witness:
            raise SceneTravelError("liveness portable witness mismatch")
    return expected


def _is_legal(session: dict[str, Any], action: dict[str, Any]) -> bool:
    try:
        _advance(session, action)
    except SceneTravelError:
        return False
    return True


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-liveness")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--demo", action="store_true")
    group.add_argument("--source-json")
    group.add_argument("--session-json")
    parser.add_argument("--max-states", type=int, default=256)
    parser.add_argument("--max-depth", type=int, default=24)
    parser.add_argument("--max-findings", type=int, default=8)
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
        result = (
            audit_liveness(
                source, session=saved, max_states=args.max_states,
                max_depth=args.max_depth, max_findings=args.max_findings,
            )
            if args.verify_json is None else verify_liveness(
                _strict_json(args.verify_json, "liveness receipt",
                             max_bytes=MAX_BYTES),
                source=source, session=saved,
            )
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
