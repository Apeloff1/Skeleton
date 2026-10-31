"""Transactional offline tournament editor with source-bound receipt replay.

This is an authoring surface, not an authority grant. Every edit is bounded,
checks the exact preceding source digest, and can be deterministically replayed
before previewing a canonical playable tournament.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.combat_tournament import (
    finish_tournament, normalize_tournament, original_tournament,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.combat_tournament_author.v1"
MAX_EDITS = 64


def new_author(source: Any) -> dict[str, Any]:
    spec = normalize_tournament(source)
    return {"schema_version": SCHEMA, "initial_source": spec,
            "source": spec, "source_digest": dig(spec), "journal": [],
            "receipt": dig({"initial_source": spec, "journal": []})}


def _normalize_edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid tournament author edit")
    kind = raw.get("kind")
    if kind == "set_stat":
        edit = _object(raw, {"kind", "entrant_id", "field", "value",
                             "expected_source_digest"}, "stat edit")
        entrant = _id(edit["entrant_id"], "entrant_id")
        field = edit["field"]
        if type(field) is not str or field not in ("max_hp", "attack", "defense", "speed"):
            raise CombatSessionError("unsupported editable tournament stat")
        limits = {"max_hp": (1, 10000), "attack": (1, 1000),
                  "defense": (0, 1000), "speed": (0, 1000)}
        value = _integer(edit["value"], field, *limits[field])
        normalized = {"kind": kind, "entrant_id": entrant, "field": field,
                      "value": value}
    elif kind == "swap_seeds":
        edit = _object(raw, {"kind", "left_id", "right_id",
                             "expected_source_digest"}, "seed edit")
        left, right = _id(edit["left_id"], "left_id"), _id(edit["right_id"], "right_id")
        if left == right:
            raise CombatSessionError("cannot swap identical seeds")
        normalized = {"kind": kind, "left_id": left, "right_id": right}
    elif kind == "set_turn_limit":
        edit = _object(raw, {"kind", "value", "expected_source_digest"},
                       "turn budget edit")
        normalized = {"kind": kind, "value": _integer(edit["value"], "turn_limit", 1, 64)}
    else:
        raise CombatSessionError("unsupported tournament author edit")
    digest = edit["expected_source_digest"]
    if type(digest) is not str or len(digest) != 64:
        raise CombatSessionError("invalid expected source digest")
    return {**normalized, "expected_source_digest": digest}


def _apply_verified(snapshot: dict[str, Any], raw_edit: Any) -> dict[str, Any]:
    if len(snapshot["journal"]) >= MAX_EDITS:
        raise CombatSessionError("tournament author edit budget exhausted")
    edit = _normalize_edit(raw_edit)
    if edit["expected_source_digest"] != snapshot["source_digest"]:
        raise CombatSessionError("stale tournament source edit")
    source = json.loads(json.dumps(snapshot["source"]))
    if edit["kind"] == "set_stat":
        actor = next((a for a in source["entrants"] if a["id"] == edit["entrant_id"]), None)
        if actor is None:
            raise CombatSessionError("unknown tournament entrant")
        actor[edit["field"]] = edit["value"]
    elif edit["kind"] == "swap_seeds":
        names = [a["id"] for a in source["entrants"]]
        if edit["left_id"] not in names or edit["right_id"] not in names:
            raise CombatSessionError("unknown tournament seed")
        left, right = names.index(edit["left_id"]), names.index(edit["right_id"])
        source["entrants"][left], source["entrants"][right] = (
            source["entrants"][right], source["entrants"][left]
        )
    else:
        source["match_turn_limit"] = edit["value"]
    spec = normalize_tournament(source)
    next_digest = dig(spec)
    event = {"sequence": len(snapshot["journal"]), "edit": edit,
             "before": snapshot["source_digest"], "after": next_digest}
    event["receipt"] = dig(event)
    journal = [*snapshot["journal"], event]
    return {"schema_version": SCHEMA, "initial_source": snapshot["initial_source"],
            "source": spec, "source_digest": next_digest, "journal": journal,
            "receipt": dig({"initial_source": snapshot["initial_source"], "journal": journal})}


def verify_author(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "initial_source", "source",
                            "source_digest", "journal", "receipt"},
                  "tournament author save")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported tournament author schema")
    rebuilt = new_author(obj["initial_source"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_EDITS:
        raise CombatSessionError("invalid tournament author journal")
    for event in journal:
        if type(event) is not dict or "edit" not in event:
            raise CombatSessionError("invalid tournament author event")
        rebuilt = _apply_verified(rebuilt, event["edit"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("tournament author edit receipt mismatch")
    if rebuilt != obj:
        raise CombatSessionError("tournament author source or replay mismatch")
    return rebuilt


def edit_author(payload: Any, edit: Any) -> dict[str, Any]:
    return _apply_verified(verify_author(payload), edit)


def preview_author(payload: Any) -> dict[str, Any]:
    saved = verify_author(payload)
    tournament = finish_tournament(saved["source"])
    record = {"schema_version": SCHEMA, "source_digest": saved["source_digest"],
              "author_receipt": saved["receipt"], "tournament": tournament}
    return {**record, "receipt": dig(record)}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton tournament-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Create original offline tournament editor save")
    create = sub.add_parser("new")
    create.add_argument("--source-json", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("--session-json", required=True)
    edit.add_argument("--edit-json", required=True)
    for name in ("verify", "preview"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--session-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = new_author(original_tournament())
        elif args.command == "new":
            result = new_author(_parse_json(args.source_json, "source"))
        else:
            session = _parse_json(args.session_json, "author session")
            if args.command == "edit":
                result = edit_author(session, _parse_json(args.edit_json, "edit"))
            elif args.command == "verify":
                result = verify_author(session)
            else:
                result = preview_author(session)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"),
                             allow_nan=False, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_CLI_BYTES:
            raise CombatSessionError("tournament author output exceeds 128 KiB")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
