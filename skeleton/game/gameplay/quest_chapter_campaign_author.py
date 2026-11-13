"""Optimistic, replay-verified editing of playable chapter campaign sources.

Edits apply to a detached canonical source and publish only when the entire
campaign remains valid. Saved games are never silently migrated between
authored revisions.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.expedition_quest import MAX_BYTES, MAX_SOURCE_BYTES, _size
from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.quest_chapter_campaign import (
    normalize_campaign, original_campaign, demo_campaign_actions,
    simulate_campaign, verify_campaign,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _object, _parse_json,
)

SCHEMA = "skeleton.quest_chapter_campaign_edit.v1"
MAX_EDITS = 32


def _copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ))
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise CombatSessionError("campaign edit is not canonical JSON") from exc


def _chapter(source: dict[str, Any], chapter_id: str) -> dict[str, Any]:
    matches = [chapter for chapter in source["chapters"]
               if chapter["id"] == chapter_id]
    if len(matches) != 1:
        raise CombatSessionError("campaign edit chapter missing or ambiguous")
    return matches[0]


def _apply(source: dict[str, Any], raw: Any) -> dict[str, Any]:
    if type(raw) is not dict or type(raw.get("op")) is not str:
        raise CombatSessionError("invalid campaign edit operation")
    op = raw["op"]
    if op == "append_chapter":
        _object(raw, {"op", "value"}, "append chapter edit")
        value = _copy(raw["value"])
        if type(value) is not dict:
            raise CombatSessionError("invalid appended chapter")
        source["chapters"].append(value)
        return {"op": op, "value": value}
    if op == "remove_last_chapter":
        _object(raw, {"op", "id"}, "remove last chapter edit")
        chapter_id = _id(raw["id"], "removed chapter")
        if len(source["chapters"]) < 2 or source["chapters"][-1]["id"] != chapter_id:
            raise CombatSessionError("only a noninitial last chapter may be removed")
        source["chapters"].pop()
        return {"op": op, "id": chapter_id}
    setters = {
        "set_required_ending": "required_ending",
        "set_required_flags": "requires_flags",
        "set_granted_flags": "grants_flags",
        "replace_quest": "quest",
    }
    if op in setters:
        _object(raw, {"op", "id", "value"}, "set chapter edit")
        chapter_id = _id(raw["id"], "edited chapter")
        value = _copy(raw["value"])
        _chapter(source, chapter_id)[setters[op]] = value
        return {"op": op, "id": chapter_id, "value": value}
    raise CombatSessionError("unsupported campaign authoring operation")


def apply_edits(
    source: Any, operations: Any, *, expected_digest: str,
    preview_actions: Any = None,
) -> dict[str, Any]:
    baseline = normalize_campaign(source)
    before = dig(baseline)
    if type(expected_digest) is not str or expected_digest != before:
        raise CombatSessionError("campaign source optimistic digest mismatch")
    if type(operations) is not list or not 1 <= len(operations) <= MAX_EDITS:
        raise CombatSessionError("invalid campaign edit batch")
    draft = _copy(baseline)
    applied = []
    for raw in operations:
        applied.append(_apply(draft, raw))
        _size(draft, MAX_SOURCE_BYTES)
    edited = normalize_campaign(draft)
    after = dig(edited)
    if before == after:
        raise CombatSessionError("campaign edit batch makes no source change")
    if preview_actions is not None:
        if type(preview_actions) is not list:
            raise CombatSessionError("invalid campaign preview action batch")
        preview_actions = _copy(preview_actions)
        preview = simulate_campaign(edited, preview_actions)
    else:
        preview = None
    receipt = {
        "schema_version": SCHEMA, "base_source": baseline,
        "before_digest": before, "operations": applied,
        "operations_digest": dig(applied),
        "source": edited, "source_digest": after,
        "preview_actions": preview_actions, "preview": preview,
    }
    _size(receipt, MAX_BYTES)
    return receipt


def verify_edits(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "base_source", "before_digest",
        "operations", "operations_digest", "source", "source_digest",
        "preview_actions", "preview",
    }, "campaign edit receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported campaign edit receipt")
    rebuilt = apply_edits(
        obj["base_source"], obj["operations"],
        expected_digest=obj["before_digest"],
        preview_actions=obj["preview_actions"],
    )
    if rebuilt != obj:
        raise CombatSessionError("campaign edit receipt replay mismatch")
    return rebuilt


def save_compatibility(receipt: Any, saved: Any) -> dict[str, Any]:
    edit = verify_edits(receipt)
    session = verify_campaign(saved)
    compatible = session["source_digest"] == edit["source_digest"]
    return {
        "schema_version": SCHEMA, "compatible": compatible,
        "old_source_digest": session["source_digest"],
        "edited_source_digest": edit["source_digest"],
        "action": "resume" if compatible else "restart_from_new_source",
    }


def original_edit_demo() -> dict[str, Any]:
    source = original_campaign()
    return apply_edits(
        source,
        [{"op": "set_granted_flags", "id": "night_watch",
          "value": ["harbor_secured", "night_shift"]}],
        expected_digest=dig(normalize_campaign(source)),
        preview_actions=demo_campaign_actions(),
    )


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton quest-campaign-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Edit a source and replay the original campaign")
    edit = sub.add_parser("edit", help="Optimistic typed source edit transaction")
    edit.add_argument("--source-json", required=True)
    edit.add_argument("--operations-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--preview-actions-json")
    verify = sub.add_parser("verify", help="Replay-check source edit receipt")
    verify.add_argument("--receipt-json", required=True)
    compat = sub.add_parser("compatibility", help="Check saved-game source identity")
    compat.add_argument("--receipt-json", required=True)
    compat.add_argument("--session-json", required=True)
    try:
        args = parser.parse_args(list(argv))
        if args.command == "demo":
            result = original_edit_demo()
        elif args.command == "edit":
            result = apply_edits(
                _parse_json(args.source_json, "campaign source"),
                _parse_json(args.operations_json, "campaign operations"),
                expected_digest=args.expected_digest,
                preview_actions=(
                    _parse_json(args.preview_actions_json, "campaign preview")
                    if args.preview_actions_json is not None else None
                ),
            )
        elif args.command == "verify":
            result = verify_edits(_parse_json(args.receipt_json, "campaign edit receipt"))
        else:
            result = save_compatibility(
                _parse_json(args.receipt_json, "campaign edit receipt"),
                _parse_json(args.session_json, "campaign save"),
            )
        _size(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
