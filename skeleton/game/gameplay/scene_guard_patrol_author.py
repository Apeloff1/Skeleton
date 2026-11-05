"""Optimistic transactional editor for playable timed patrol source.

An edit is a complete source transaction. Replay verifies each digest lease
and revalidates authored geometry before any revised source is published.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_guard_patrol import (
    _bounded, inspect_patrol, normalize_patrol,
    original_patrol, simulate_patrol,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _object, _limit

SCHEMA = "skeleton.scene_guard_patrol_author.v1"
BUNDLE = "skeleton.scene_guard_patrol_author_bundle.v1"
MAX_EDITS = 32


def new_author(source: Any) -> dict[str, Any]:
    spec = normalize_patrol(source)
    result = {
        "schema_version": SCHEMA, "initial_source": spec, "source": spec,
        "source_digest": dig(spec), "journal": [],
    }
    result["receipt"] = dig({"initial_source": spec, "journal": []})
    _bounded(result)
    return result


def _edit(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid patrol author edit")
    kind = raw.get("kind")
    if kind == "set_offset":
        obj = _object(raw, {"kind", "guard_id", "value",
                            "expected_source_digest"}, "offset edit")
        edit = {"kind": kind, "guard_id": _id(obj["guard_id"], "guard id"),
                "value": _limit(obj["value"], "offset", 0, 7)}
    elif kind == "set_bypass":
        obj = _object(raw, {"kind", "guard_id", "item_id",
                            "expected_source_digest"}, "bypass edit")
        item = obj["item_id"]
        edit = {"kind": kind, "guard_id": _id(obj["guard_id"], "guard id"),
                "item_id": None if item is None else _id(item, "item id")}
    elif kind == "set_exit_block":
        obj = _object(raw, {"kind", "guard_id", "scene_id", "exit_id",
                            "blocked", "expected_source_digest"}, "block edit")
        if type(obj["blocked"]) is not bool:
            raise SceneTravelError("blocked flag must be boolean")
        edit = {
            "kind": kind, "guard_id": _id(obj["guard_id"], "guard id"),
            "scene_id": _id(obj["scene_id"], "scene id"),
            "exit_id": _id(obj["exit_id"], "exit id"), "blocked": obj["blocked"],
        }
    elif kind == "rename_patrol":
        obj = _object(raw, {"kind", "patrol_id",
                            "expected_source_digest"}, "rename edit")
        edit = {"kind": kind, "patrol_id": _id(obj["patrol_id"], "patrol id")}
    else:
        raise SceneTravelError("unsupported patrol author edit")
    lease = obj["expected_source_digest"]
    if type(lease) is not str or len(lease) != 64:
        raise SceneTravelError("invalid expected source digest")
    return {**edit, "expected_source_digest": lease}


def _apply_verified(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    if len(snapshot["journal"]) >= MAX_EDITS:
        raise SceneTravelError("patrol author edit budget exceeded")
    edit = _edit(raw)
    if edit["expected_source_digest"] != snapshot["source_digest"]:
        raise SceneTravelError("stale patrol source edit")
    source = json.loads(_bounded(snapshot["source"]).decode("utf-8"))
    if edit["kind"] == "rename_patrol":
        source["patrol_id"] = edit["patrol_id"]
    else:
        guard = next((g for g in source["guards"] if g["id"] == edit["guard_id"]), None)
        if guard is None:
            raise SceneTravelError("unknown patrol guard")
        if edit["kind"] == "set_offset":
            guard["offset"] = edit["value"]
        elif edit["kind"] == "set_bypass":
            guard["bypass_item"] = edit["item_id"]
        else:
            edge = {"scene_id": edit["scene_id"], "exit_id": edit["exit_id"]}
            present = edge in guard["blocked_exits"]
            if edit["blocked"] and not present:
                guard["blocked_exits"].append(edge)
            elif not edit["blocked"] and present:
                guard["blocked_exits"].remove(edge)
            else:
                raise SceneTravelError("patrol block edit has no effect")
    spec = normalize_patrol(source)
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
        "receipt": dig({"initial_source": snapshot["initial_source"], "journal": journal}),
    }
    _bounded(result)
    return result


def verify_author(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "initial_source", "source",
                        "source_digest", "journal", "receipt"}, "patrol author")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported patrol author schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_EDITS:
        raise SceneTravelError("invalid patrol author journal")
    rebuilt = new_author(obj["initial_source"])
    for event in journal:
        if type(event) is not dict or "edit" not in event:
            raise SceneTravelError("invalid patrol author event")
        rebuilt = _apply_verified(rebuilt, event["edit"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("patrol author replay mismatch")
    if rebuilt != obj:
        raise SceneTravelError("patrol author source or receipt mismatch")
    return rebuilt


def edit_author(raw: Any, edit: Any) -> dict[str, Any]:
    return _apply_verified(verify_author(raw), edit)


def preview_author(raw: Any, actions: Any) -> dict[str, Any]:
    author = verify_author(raw)
    if type(actions) is not list or len(actions) > 64:
        raise SceneTravelError("invalid patrol preview actions")
    session = simulate_patrol(author["source"], actions)
    result = {
        "schema_version": SCHEMA, "author_receipt": author["receipt"],
        "source_digest": author["source_digest"],
        "session": session, "view": inspect_patrol(session),
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
                        "author_receipt", "author", "checksum"}, "patrol author bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported patrol author bundle")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("patrol author bundle checksum mismatch")
    author = verify_author(obj["author"])
    if (obj["source_digest"] != author["source_digest"]
            or obj["author_receipt"] != author["receipt"]):
        raise SceneTravelError("patrol author bundle source mismatch")
    return author


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-patrol-author")
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
            p.add_argument("--actions-json", default="[]")
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = new_author(original_patrol())
        elif args.command == "new":
            result = new_author(_strict_json(args.source_json, "patrol source"))
        elif args.command == "import":
            result = import_author(_strict_json(args.bundle_json, "author bundle"))
        else:
            author = _strict_json(args.author_json, "patrol author")
            if args.command == "edit":
                result = edit_author(author, _strict_json(args.edit_json, "author edit"))
            elif args.command == "verify":
                result = verify_author(author)
            elif args.command == "preview":
                result = preview_author(author, _strict_json(args.actions_json, "preview actions"))
            else:
                result = export_author(author)
        print(_bounded(result).decode("utf-8"))
        return 0
    except (SceneTravelError, KeyError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
