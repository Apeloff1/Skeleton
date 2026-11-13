"""Bounded one-turn quest decision previews with canonical playable receipts.

A preview never mutates a save or grants rewards. Applying a choice requires
an exact state-digest lease and canonical legal-action membership; each
portable result is replayed before publication.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import (
    _advance, export_quest, import_quest, new_quest, original_quest, verify_quest,
)
from skeleton.game.gameplay.expedition_quest_interactive import legal_quest_actions
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _parse_json

SCHEMA = "skeleton.quest_decision_preview.v1"
RECEIPT_SCHEMA = "skeleton.quest_decision_receipt.v1"
MAX_PREVIEWS = 24
MAX_BYTES = 5 * 1024 * 1024


def _bounded(payload: Any) -> None:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("invalid quest decision JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise CombatSessionError("quest decision output exceeds size budget")


def _session(source: Any, session: Any) -> dict[str, Any]:
    if (source is None) == (session is None):
        raise CombatSessionError("supply exactly one quest source or session")
    return new_quest(source) if session is None else verify_quest(session)


def _state_summary(session: dict[str, Any]) -> dict[str, Any]:
    state = session["state"]
    expedition = state["expedition"]["state"]
    return {
        "tick": state["tick"], "phase": state["phase"],
        "location": state["location"], "ending": state["ending"],
        "choices": dict(sorted(state["choices"].items())),
        "items": dict(sorted(state["items"].items())),
        "crafted": list(state["crafted"]),
        "combat_phase": expedition["phase"],
        "hero_hp": expedition["hero_hp"],
        "currency": expedition["currency"],
        "inventory": dict(sorted(expedition["inventory"].items())),
    }


def preview_decisions(source: Any = None, *, session: Any = None,
                      limit: int = 12) -> dict[str, Any]:
    """Preview real legal transitions, never an imagined or forged outcome."""
    if type(limit) is not int or not 1 <= limit <= MAX_PREVIEWS:
        raise CombatSessionError("invalid quest preview limit")
    start = _session(source, session)
    actions = legal_quest_actions(start)
    candidates = []
    for action in actions[:limit]:
        try:
            next_state = _advance(start, action)
            bundle = export_quest(next_state)
            if import_quest(bundle) != next_state:
                raise CombatSessionError("quest preview portable replay mismatch")
        except CombatSessionError as exc:
            # A visible move can still be rejected by the canonical engine.
            candidates.append({"action": action, "status": "rejected",
                               "reason": str(exc)})
            continue
        candidates.append({
            "action": action, "status": "playable",
            "state_digest": next_state["state_digest"],
            "portable_checksum": bundle["checksum"],
            "state": _state_summary(next_state),
        })
    result = {
        "schema_version": SCHEMA,
        "source_digest": start["source_digest"],
        "initial_state_digest": start["state_digest"],
        "initial_state": _state_summary(start),
        "available_count": len(actions),
        "preview_count": len(candidates),
        "truncated": len(actions) > limit,
        "limit": limit,
        "candidates": candidates,
    }
    result["checksum"] = dig(result)
    _bounded(result)
    return result


def apply_decision(payload: Any, action: Any, *,
                   expected_state_digest: str) -> dict[str, Any]:
    """Compare-and-swap the verified game state and export the earned result."""
    start = verify_quest(payload)
    if (type(expected_state_digest) is not str
            or expected_state_digest != start["state_digest"]):
        raise CombatSessionError("stale quest decision state digest")
    if type(action) is not dict or action not in legal_quest_actions(start):
        raise CombatSessionError("quest decision is not a legal visible action")
    next_state = _advance(start, action)
    bundle = export_quest(next_state)
    if import_quest(bundle) != next_state:
        raise CombatSessionError("quest decision export replay mismatch")
    record = {
        "schema_version": RECEIPT_SCHEMA,
        "source_digest": start["source_digest"],
        "before_state_digest": start["state_digest"],
        "after_state_digest": next_state["state_digest"],
        "before": start,
        "action": next_state["journal"][-1]["action"],
        "after_bundle": bundle,
    }
    record["checksum"] = dig(record)
    _bounded(record)
    return record


def verify_decision(payload: Any) -> dict[str, Any]:
    """Reapply a recorded choice; reject forged rewards and changed receipts."""
    _bounded(payload)
    if type(payload) is not dict or set(payload) != {
        "schema_version", "source_digest", "before_state_digest",
        "after_state_digest", "before", "action", "after_bundle", "checksum",
    } or payload["schema_version"] != RECEIPT_SCHEMA:
        raise CombatSessionError("invalid quest decision receipt")
    expected = apply_decision(
        payload["before"], payload["action"],
        expected_state_digest=payload["before_state_digest"],
    )
    if payload != expected:
        raise CombatSessionError("quest decision replay or receipt mismatch")
    return import_quest(expected["after_bundle"])


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-decisions")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview")
    start = preview.add_mutually_exclusive_group(required=True)
    start.add_argument("--demo", action="store_true")
    start.add_argument("--source-json")
    start.add_argument("--session-json")
    preview.add_argument("--limit", type=int, default=12)
    apply = sub.add_parser("apply")
    apply.add_argument("--session-json", required=True)
    apply.add_argument("--action-json", required=True)
    apply.add_argument("--expected-state-digest", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--receipt-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "preview":
            result = preview_decisions(
                original_quest() if args.demo else
                _parse_json(args.source_json, "quest source")
                if args.source_json is not None else None,
                session=_parse_json(args.session_json, "quest session")
                if args.session_json is not None else None,
                limit=args.limit,
            )
        elif args.command == "apply":
            result = apply_decision(
                _parse_json(args.session_json, "quest session"),
                _parse_json(args.action_json, "quest action"),
                expected_state_digest=args.expected_state_digest,
            )
        else:
            saved = verify_decision(_parse_json(args.receipt_json, "decision receipt"))
            result = {"ok": True, "source_digest": saved["source_digest"],
                      "state_digest": saved["state_digest"],
                      "phase": saved["state"]["phase"]}
        _bounded(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
