"""Transactional career editor with source-leased training and playable preview."""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _id, _integer, _object
from skeleton.game.gameplay.combat_league import _bounded, _json
from skeleton.game.gameplay.combat_league_career import (
    career_board, finish_career, normalize_career, original_career,
)

SCHEMA = "skeleton.combat_league_career_author.v1"
BUNDLE = "skeleton.combat_league_career_author_bundle.v1"
MAX_EDITS = 32
STATS = {"max_hp": (1, 10000), "attack": (1, 1000),
         "defense": (0, 1000), "speed": (0, 1000)}


def new_author(source: Any) -> dict[str, Any]:
    spec = normalize_career(source)
    record = {
        "schema_version": SCHEMA, "initial_source": spec,
        "source": spec, "source_digest": dig(spec), "journal": [],
    }
    record["receipt"] = dig({"initial_source": spec, "journal": []})
    _bounded(record)
    return record


def _edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid career author edit")
    kind = raw.get("kind")
    if kind == "rename_career":
        obj = _object(raw, {"kind", "career_id", "expected_source_digest"},
                      "career rename")
        result = {"kind": kind, "career_id": _id(obj["career_id"], "career_id")}
    elif kind in ("set_seasons", "set_training_tokens", "set_league_rounds"):
        obj = _object(raw, {"kind", "value", "expected_source_digest"},
                      "career budget edit")
        low = 0 if kind == "set_training_tokens" else 1
        result = {"kind": kind, "value": _integer(obj["value"], kind, low, 4)}
    elif kind == "set_entrant_stat":
        obj = _object(raw, {"kind", "entrant_id", "field", "value",
                            "expected_source_digest"}, "career stat edit")
        field = obj["field"]
        if type(field) is not str or field not in STATS:
            raise CombatSessionError("unsupported career actor stat")
        result = {
            "kind": kind, "entrant_id": _id(obj["entrant_id"], "entrant_id"),
            "field": field, "value": _integer(obj["value"], field, *STATS[field]),
        }
    else:
        raise CombatSessionError("unsupported career author edit")
    lease = obj["expected_source_digest"]
    if type(lease) is not str or len(lease) != 64:
        raise CombatSessionError("invalid expected source digest")
    return {**result, "expected_source_digest": lease}


def _apply_verified(record: dict[str, Any], raw: Any) -> dict[str, Any]:
    if len(record["journal"]) >= MAX_EDITS:
        raise CombatSessionError("career author edit budget exceeded")
    edit = _edit(raw)
    if edit["expected_source_digest"] != record["source_digest"]:
        raise CombatSessionError("stale career source edit")
    source = json.loads(_bounded(record["source"]).decode("utf-8"))
    if edit["kind"] == "rename_career":
        source["career_id"] = edit["career_id"]
    elif edit["kind"] == "set_seasons":
        source["seasons"] = edit["value"]
    elif edit["kind"] == "set_training_tokens":
        source["training_tokens"] = edit["value"]
    elif edit["kind"] == "set_league_rounds":
        source["league"]["rounds"] = edit["value"]
    else:
        entrant = next((e for e in source["league"]["entrants"]
                        if e["id"] == edit["entrant_id"]), None)
        if entrant is None:
            raise CombatSessionError("unknown career entrant")
        entrant[edit["field"]] = edit["value"]
    spec = normalize_career(source)
    after = dig(spec)
    event = {
        "sequence": len(record["journal"]), "edit": edit,
        "before": record["source_digest"], "after": after,
    }
    event["receipt"] = dig(event)
    journal = [*record["journal"], event]
    result = {
        "schema_version": SCHEMA, "initial_source": record["initial_source"],
        "source": spec, "source_digest": after, "journal": journal,
        "receipt": dig({"initial_source": record["initial_source"], "journal": journal}),
    }
    _bounded(result)
    return result


def verify_author(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "initial_source", "source",
                        "source_digest", "journal", "receipt"}, "career author")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported career author schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_EDITS:
        raise CombatSessionError("invalid career author journal")
    rebuilt = new_author(obj["initial_source"])
    for event in journal:
        if type(event) is not dict or "edit" not in event:
            raise CombatSessionError("invalid career author event")
        rebuilt = _apply_verified(rebuilt, event["edit"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("career author event replay mismatch")
    if rebuilt != obj:
        raise CombatSessionError("career author source or receipt mismatch")
    return rebuilt


def edit_author(raw: Any, edit: Any) -> dict[str, Any]:
    return _apply_verified(verify_author(raw), edit)


def preview_author(raw: Any, choices: Any) -> dict[str, Any]:
    author = verify_author(raw)
    session = finish_career(author["source"], choices)
    result = {
        "schema_version": SCHEMA, "author_receipt": author["receipt"],
        "source_digest": author["source_digest"], "session": session,
        "board": career_board(session),
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def export_author(raw: Any) -> dict[str, Any]:
    author = verify_author(raw)
    bundle = {
        "schema_version": BUNDLE, "source_digest": author["source_digest"],
        "author_receipt": author["receipt"], "author": author,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_author(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "source_digest",
                        "author_receipt", "author", "checksum"}, "career author bundle")
    if obj["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported career author bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("career author bundle checksum mismatch")
    author = verify_author(obj["author"])
    if (obj["source_digest"] != author["source_digest"]
            or obj["author_receipt"] != author["receipt"]):
        raise CombatSessionError("career author bundle source mismatch")
    return author


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-career-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    new = sub.add_parser("new")
    new.add_argument("--source-json", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("--author-json", required=True)
    edit.add_argument("--edit-json", required=True)
    for name in ("verify", "preview", "export"):
        p = sub.add_parser(name)
        p.add_argument("--author-json", required=True)
        if name == "preview":
            p.add_argument("--choices-json", default="[]")
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = new_author(original_career())
        elif args.command == "new":
            result = new_author(_json(args.source_json, "career source"))
        elif args.command == "import":
            result = import_author(_json(args.bundle_json, "career author bundle"))
        else:
            author = _json(args.author_json, "career author")
            if args.command == "edit":
                result = edit_author(author, _json(args.edit_json, "career edit"))
            elif args.command == "verify":
                result = verify_author(author)
            elif args.command == "preview":
                result = preview_author(author, _json(args.choices_json, "career choices"))
            else:
                result = export_author(author)
        print(_bounded(result).decode("utf-8"))
        return 0
    except (CombatSessionError, KeyError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
