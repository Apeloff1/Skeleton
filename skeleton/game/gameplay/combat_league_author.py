"""Transactional eight-entrant league editor with canonical replay and preview.

Editing is source-digest leased; a stale or invalid edit never mutates source.
The replay journal detects drift, not the external identity of an author.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.turn_combat import CombatSessionError, _id, _integer, _object
from skeleton.game.gameplay.combat_league import (
    SCHEMA as LEAGUE_SCHEMA, _bounded, _json, finish_league,
    normalize_league, original_league, standings,
)

SCHEMA = "skeleton.combat_league_author.v1"
BUNDLE = "skeleton.combat_league_author_bundle.v1"
MAX_EDITS = 32
STATS = {
    "max_hp": (1, 10000), "attack": (1, 1000),
    "defense": (0, 1000), "speed": (0, 1000),
}


def new_author(source: Any) -> dict[str, Any]:
    spec = normalize_league(source)
    record = {
        "schema_version": SCHEMA, "initial_source": spec, "source": spec,
        "source_digest": dig(spec), "journal": [],
    }
    record["receipt"] = dig({"initial_source": spec, "journal": []})
    _bounded(record)
    return record


def _edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid league author edit")
    kind = raw.get("kind")
    if kind == "set_stat":
        obj = _object(raw, {
            "kind", "entrant_id", "field", "value", "expected_source_digest",
        }, "league stat edit")
        field = obj["field"]
        if type(field) is not str or field not in STATS:
            raise CombatSessionError("unsupported league stat")
        result = {
            "kind": kind, "entrant_id": _id(obj["entrant_id"], "entrant_id"),
            "field": field, "value": _integer(obj["value"], field, *STATS[field]),
        }
    elif kind == "rename_entrant":
        obj = _object(raw, {
            "kind", "entrant_id", "new_id", "expected_source_digest",
        }, "league rename edit")
        result = {
            "kind": kind, "entrant_id": _id(obj["entrant_id"], "entrant_id"),
            "new_id": _id(obj["new_id"], "new_id"),
        }
    elif kind == "set_rounds":
        obj = _object(raw, {"kind", "value", "expected_source_digest"},
                      "league rounds edit")
        result = {"kind": kind, "value": _integer(obj["value"], "rounds", 1, 4)}
    elif kind == "set_turn_limit":
        obj = _object(raw, {"kind", "value", "expected_source_digest"},
                      "league turn limit edit")
        result = {"kind": kind, "value": _integer(obj["value"], "turn_limit", 1, 64)}
    else:
        raise CombatSessionError("unsupported league author edit")
    digest = obj["expected_source_digest"]
    if type(digest) is not str or len(digest) != 64:
        raise CombatSessionError("invalid expected source digest")
    return {**result, "expected_source_digest": digest}


def _apply_verified(snapshot: dict[str, Any], raw_edit: Any) -> dict[str, Any]:
    if len(snapshot["journal"]) >= MAX_EDITS:
        raise CombatSessionError("league author edit budget exceeded")
    edit = _edit(raw_edit)
    if edit["expected_source_digest"] != snapshot["source_digest"]:
        raise CombatSessionError("stale league source edit")
    source = json.loads(json.dumps(snapshot["source"]))
    if edit["kind"] in ("set_stat", "rename_entrant"):
        entrant = next((e for e in source["entrants"]
                        if e["id"] == edit["entrant_id"]), None)
        if entrant is None:
            raise CombatSessionError("unknown league entrant")
        if edit["kind"] == "set_stat":
            entrant[edit["field"]] = edit["value"]
        else:
            entrant["id"] = edit["new_id"]
    elif edit["kind"] == "set_rounds":
        source["rounds"] = edit["value"]
    else:
        source["match_turn_limit"] = edit["value"]
    spec = normalize_league(source)
    after = dig(spec)
    event = {
        "sequence": len(snapshot["journal"]), "edit": edit,
        "before": snapshot["source_digest"], "after": after,
    }
    event["receipt"] = dig(event)
    journal = [*snapshot["journal"], event]
    result = {
        "schema_version": SCHEMA, "initial_source": snapshot["initial_source"],
        "source": spec, "source_digest": after, "journal": journal,
        "receipt": dig({"initial_source": snapshot["initial_source"],
                        "journal": journal}),
    }
    _bounded(result)
    return result


def verify_author(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "initial_source", "source", "source_digest",
        "journal", "receipt",
    }, "league author session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported league author schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_EDITS:
        raise CombatSessionError("invalid league author journal")
    rebuilt = new_author(obj["initial_source"])
    for event in journal:
        if type(event) is not dict or "edit" not in event:
            raise CombatSessionError("invalid league author event")
        rebuilt = _apply_verified(rebuilt, event["edit"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("league author event replay mismatch")
    if rebuilt != obj:
        raise CombatSessionError("league author source or receipt mismatch")
    return rebuilt


def edit_author(payload: Any, edit: Any) -> dict[str, Any]:
    return _apply_verified(verify_author(payload), edit)


def preview_author(payload: Any) -> dict[str, Any]:
    author = verify_author(payload)
    league = finish_league(author["source"])
    result = {
        "schema_version": SCHEMA, "author_receipt": author["receipt"],
        "source_digest": author["source_digest"], "league": league,
        "standings": standings(league),
    }
    result["receipt"] = dig(result)
    _bounded(result)
    return result


def export_author(payload: Any) -> dict[str, Any]:
    record = verify_author(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": record["source_digest"],
        "author_receipt": record["receipt"], "author": record,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_author(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "source_digest", "author_receipt", "author", "checksum",
    }, "league author bundle")
    if obj["schema_version"] != BUNDLE:
        raise CombatSessionError("unsupported league author bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise CombatSessionError("league author bundle checksum mismatch")
    author = verify_author(obj["author"])
    if (obj["source_digest"] != author["source_digest"]
            or obj["author_receipt"] != author["receipt"]):
        raise CombatSessionError("league author bundle source mismatch")
    return author


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-league-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    new = sub.add_parser("new")
    new.add_argument("--source-json", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("--author-json", required=True)
    edit.add_argument("--edit-json", required=True)
    for name in ("verify", "preview", "export"):
        sub.add_parser(name).add_argument("--author-json", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = new_author(original_league())
        elif args.command == "new":
            result = new_author(_json(args.source_json, "league source"))
        elif args.command == "import":
            result = import_author(_json(args.bundle_json, "author bundle"))
        else:
            author = _json(args.author_json, "author session")
            if args.command == "edit":
                result = edit_author(author, _json(args.edit_json, "edit"))
            elif args.command == "verify":
                result = verify_author(author)
            elif args.command == "preview":
                result = preview_author(author)
            else:
                result = export_author(author)
        print(_bounded(result).decode("utf-8"))
        return 0
    except (CombatSessionError, KeyError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
