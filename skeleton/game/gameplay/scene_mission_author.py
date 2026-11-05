"""Transactional authored mission editor with canonical playable preview.

Edits are data-only and digest-leased. The journal is replayed from the
original source before any new edit or preview. No save, quest completion or
reputation is granted by editor operations.
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
    MAX_BYTES, MAX_SOURCE_BYTES, demo_actions, export_mission, import_mission,
    normalize_mission_world, original_mission, simulate_mission,
)
from skeleton.game.gameplay.scene_mission_consequences import inspect_consequences
from skeleton.game.gameplay.scene_travel import (
    MAX_STEPS, SceneTravelError, _id, _limit, _object,
)

SCHEMA = "skeleton.scene_mission_author.v1"
MAX_EDITS = 64
MAX_BATCH = 16


def _bound(payload: Any) -> None:
    try:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid mission editor JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise SceneTravelError("mission editor byte budget exceeded")


def _apply_one(source: dict[str, Any], raw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a typed edit, then re-normalize the entire authored graph."""
    if type(raw) is not dict:
        raise SceneTravelError("invalid mission editor operation")
    kind = raw.get("kind")
    if type(kind) is not str:
        raise SceneTravelError("invalid mission editor operation kind")
    fields = {
        "choice_reputation": {"kind", "choice_id", "option_id", "reputation"},
        "mission_reputation": {"kind", "mission_id", "reputation"},
        "ending_threshold": {"kind", "ending_id", "min_reputation"},
        "step_limit": {"kind", "step_limit"},
        "exit_requirement": {"kind", "scene_id", "exit_id", "requires_item"},
        "pickup_item": {"kind", "scene_id", "pickup_id", "item_id"},
    }
    if kind not in fields:
        raise SceneTravelError("unsupported mission editor operation")
    _object(raw, fields[kind], "mission editor operation")
    edit = dict(raw)
    if kind == "choice_reputation":
        edit["choice_id"] = _id(raw["choice_id"], "choice_id")
        edit["option_id"] = _id(raw["option_id"], "option_id")
        edit["reputation"] = _limit(raw["reputation"], "reputation", -100, 100)
    elif kind == "mission_reputation":
        edit["mission_id"] = _id(raw["mission_id"], "mission_id")
        edit["reputation"] = _limit(raw["reputation"], "reputation", 0, 1000)
    elif kind == "ending_threshold":
        edit["ending_id"] = _id(raw["ending_id"], "ending_id")
        edit["min_reputation"] = _limit(raw["min_reputation"], "ending reputation", -10000, 10000)
    elif kind == "step_limit":
        edit["step_limit"] = _limit(raw["step_limit"], "step_limit", 1, MAX_STEPS)
    elif kind == "exit_requirement":
        edit["scene_id"] = _id(raw["scene_id"], "scene_id")
        edit["exit_id"] = _id(raw["exit_id"], "exit_id")
        edit["requires_item"] = (
            None if raw["requires_item"] is None else
            _id(raw["requires_item"], "requires_item")
        )
    else:
        edit["scene_id"] = _id(raw["scene_id"], "scene_id")
        edit["pickup_id"] = _id(raw["pickup_id"], "pickup_id")
        edit["item_id"] = _id(raw["item_id"], "item_id")
    changed = json.loads(json.dumps(source))
    found = False
    if kind == "choice_reputation":
        for choice in changed["choices"]:
            if choice["id"] == edit["choice_id"]:
                for option in choice["options"]:
                    if option["id"] == edit["option_id"]:
                        option["reputation"] = edit["reputation"]
                        found = True
    elif kind == "mission_reputation":
        for mission in changed["missions"]:
            if mission["id"] == edit["mission_id"]:
                mission["reputation"] = edit["reputation"]
                found = True
    elif kind == "ending_threshold":
        for ending in changed["endings"]:
            if ending["id"] == edit["ending_id"]:
                ending["min_reputation"] = edit["min_reputation"]
                found = True
    elif kind == "step_limit":
        changed["world"]["step_limit"] = edit["step_limit"]
        found = True
    else:
        for scene in changed["world"]["scenes"]:
            if scene["id"] == edit["scene_id"]:
                collection = "exits" if kind == "exit_requirement" else "pickups"
                key = "exit_id" if kind == "exit_requirement" else "pickup_id"
                for item in scene[collection]:
                    if item["id"] == edit[key]:
                        if kind == "exit_requirement":
                            item["requires_item"] = edit["requires_item"]
                        else:
                            item["item_id"] = edit["item_id"]
                        found = True
    if not found:
        raise SceneTravelError("mission editor target not found")
    normalized = normalize_mission_world(changed)
    if normalized == source:
        raise SceneTravelError("mission editor no-op")
    return normalized, edit


def _seal(record: dict[str, Any]) -> dict[str, Any]:
    result = {**record, "digest": dig(record)}
    _bound(result)
    return result


def new_editor(source: Any) -> dict[str, Any]:
    spec = normalize_mission_world(source)
    return _seal({
        "schema_version": SCHEMA,
        "base_source": spec, "base_digest": dig(spec),
        "source": spec, "source_digest": dig(spec),
        "revision": 0, "journal": [],
    })


def verify_editor(payload: Any) -> dict[str, Any]:
    _bound(payload)
    obj = _object(payload, {
        "schema_version", "base_source", "base_digest",
        "source", "source_digest", "revision", "journal", "digest",
    }, "mission editor")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported mission editor schema")
    base = normalize_mission_world(obj["base_source"])
    if base != obj["base_source"] or dig(base) != obj["base_digest"]:
        raise SceneTravelError("mission editor base source mismatch")
    journal = obj["journal"]
    if (type(journal) is not list or len(journal) > MAX_EDITS
            or type(obj["revision"]) is not int
            or obj["revision"] != len(journal)):
        raise SceneTravelError("invalid mission editor journal or revision")
    source = base
    for sequence, entry in enumerate(journal):
        _object(entry, {"sequence", "edit", "before", "after", "receipt"},
                "mission editor event")
        if entry["sequence"] != sequence or entry["before"] != dig(source):
            raise SceneTravelError("mission editor event lineage mismatch")
        source, edit = _apply_one(source, entry["edit"])
        record = {"sequence": sequence, "edit": edit,
                  "before": entry["before"], "after": dig(source)}
        if entry != {**record, "receipt": dig(record)}:
            raise SceneTravelError("mission editor event receipt mismatch")
    if (source != obj["source"] or dig(source) != obj["source_digest"]
            or obj["digest"] != dig({k: v for k, v in obj.items() if k != "digest"})):
        raise SceneTravelError("mission editor source or digest mismatch")
    return obj


def apply_edits(payload: Any, edits: Any, *, expected_revision: int,
                expected_digest: str) -> dict[str, Any]:
    record = verify_editor(payload)
    if (type(expected_revision) is not int or expected_revision != record["revision"]
            or type(expected_digest) is not str or expected_digest != record["digest"]):
        raise SceneTravelError("stale mission editor revision or digest")
    if (type(edits) is not list or not 1 <= len(edits) <= MAX_BATCH
            or len(edits) + record["revision"] > MAX_EDITS):
        raise SceneTravelError("mission editor batch budget exceeded")
    source = record["source"]
    journal = list(record["journal"])
    for raw in edits:
        before = dig(source)
        source, edit = _apply_one(source, raw)
        event = {"sequence": len(journal), "edit": edit,
                 "before": before, "after": dig(source)}
        journal.append({**event, "receipt": dig(event)})
    updated = _seal({
        "schema_version": SCHEMA,
        "base_source": record["base_source"], "base_digest": record["base_digest"],
        "source": source, "source_digest": dig(source),
        "revision": len(journal), "journal": journal,
    })
    return verify_editor(updated)


def preview_editor(payload: Any, actions: Any) -> dict[str, Any]:
    editor = verify_editor(payload)
    session = simulate_mission(editor["source"], actions)
    bundle = export_mission(session)
    if import_mission(bundle) != session:
        raise SceneTravelError("mission editor preview export mismatch")
    consequences = inspect_consequences(session)
    report = {
        "schema_version": SCHEMA, "revision": editor["revision"],
        "editor_digest": editor["digest"],
        "source_digest": editor["source_digest"],
        "state_digest": session["state_digest"],
        "phase": session["state"]["phase"], "ending": session["state"]["ending"],
        "reputation": session["state"]["reputation"],
        "missions": list(session["state"]["missions"]),
        "bundle_checksum": bundle["checksum"],
        "consequence_receipt": consequences["receipt"],
    }
    report["receipt"] = dig(report)
    _bound(report)
    return report


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    init = sub.add_parser("new")
    init.add_argument("--source-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--editor-json", required=True)
    apply = sub.add_parser("apply")
    apply.add_argument("--editor-json", required=True)
    apply.add_argument("--edits-json", required=True)
    apply.add_argument("--expected-revision", type=int, required=True)
    apply.add_argument("--expected-digest", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--editor-json", required=True)
    preview.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = preview_editor(new_editor(original_mission()), demo_actions())
        elif args.command == "new":
            result = new_editor(_strict_json(args.source_json, "mission source",
                                             max_bytes=MAX_SOURCE_BYTES))
        else:
            editor = _strict_json(args.editor_json, "mission editor", max_bytes=MAX_BYTES)
            if args.command == "verify":
                result = verify_editor(editor)
            elif args.command == "apply":
                result = apply_edits(
                    editor, _strict_json(args.edits_json, "mission edits",
                                         max_bytes=MAX_SOURCE_BYTES),
                    expected_revision=args.expected_revision,
                    expected_digest=args.expected_digest,
                )
            else:
                result = preview_editor(
                    editor, _strict_json(args.actions_json, "mission actions",
                                         max_bytes=MAX_SOURCE_BYTES),
                )
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
