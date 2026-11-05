"""Transactional tile survival editor with replay-bound playable previews.

Every edit is validated against canonical tile topology before publication.
A stale source revision never overwrites another editor's authored changes.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_tile_survival import (
    MAX_BYTES, _bounded, _json, export_survival, normalize_survival,
    original_survival, simulate_survival,
)
from skeleton.game.gameplay.scene_tile_survival_route import solve_survival
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _limit, _object,
)

SCHEMA = "skeleton.scene_tile_survival_author.v1"
MAX_EDITS = 64


def _edit(source: dict[str, Any], raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid survival source edit")
    kind = raw.get("kind")
    spec = {
        **source,
        "hazards": [dict(x) for x in source["hazards"]],
        "camps": [dict(x) for x in source["camps"]],
        "food_pickups": list(source["food_pickups"]),
    }
    if kind in ("set_health", "set_food_capacity", "set_initial_food", "set_turn_limit"):
        _object(raw, {"kind", "value"}, "survival scalar edit")
        field, low, high = {
            "set_health": ("max_health", 1, 100),
            "set_food_capacity": ("max_food", 1, 32),
            "set_initial_food": ("initial_food", 0, 32),
            "set_turn_limit": ("turn_limit", 1, 256),
        }[kind]
        spec[field] = _limit(raw["value"], field, low, high)
    elif kind in ("set_hazard", "remove_hazard"):
        required = (
            {"kind", "scene_id", "at", "damage"}
            if kind == "set_hazard" else {"kind", "scene_id", "at"}
        )
        _object(raw, required, "survival hazard edit")
        scene_id = _id(raw["scene_id"], "hazard scene")
        point = raw["at"]
        if type(point) is not list or len(point) != 2:
            raise SceneTravelError("invalid hazard edit coordinate")
        existing = [
            h for h in spec["hazards"]
            if h["scene_id"] == scene_id and h["at"] == point
        ]
        if kind == "remove_hazard":
            if not existing:
                raise SceneTravelError("survival hazard not authored")
            spec["hazards"] = [
                h for h in spec["hazards"]
                if h["scene_id"] != scene_id or h["at"] != point
            ]
        else:
            damage = _limit(raw["damage"], "hazard damage", 1, 100)
            spec["hazards"] = [
                h for h in spec["hazards"]
                if h["scene_id"] != scene_id or h["at"] != point
            ]
            spec["hazards"].append({
                "scene_id": scene_id, "at": point, "damage": damage,
            })
    elif kind in ("add_camp", "remove_camp"):
        _object(raw, {"kind", "scene_id", "at"}, "survival camp edit")
        scene_id = _id(raw["scene_id"], "camp scene")
        point = raw["at"]
        if type(point) is not list or len(point) != 2:
            raise SceneTravelError("invalid camp edit coordinate")
        existing = any(
            c["scene_id"] == scene_id and c["at"] == point
            for c in spec["camps"]
        )
        if kind == "add_camp":
            if existing:
                raise SceneTravelError("survival camp already authored")
            spec["camps"].append({"scene_id": scene_id, "at": point})
        else:
            if not existing:
                raise SceneTravelError("survival camp not authored")
            spec["camps"] = [
                c for c in spec["camps"]
                if c["scene_id"] != scene_id or c["at"] != point
            ]
    elif kind in ("add_food", "remove_food"):
        _object(raw, {"kind", "pickup"}, "survival food edit")
        pickup = _id(raw["pickup"], "food pickup")
        exists = pickup in spec["food_pickups"]
        if kind == "add_food":
            if exists:
                raise SceneTravelError("survival food already authored")
            spec["food_pickups"].append(pickup)
        else:
            if not exists:
                raise SceneTravelError("survival food not authored")
            spec["food_pickups"].remove(pickup)
    else:
        raise SceneTravelError("unsupported survival source edit")
    return normalize_survival(spec)


def _seal(document: dict[str, Any]) -> dict[str, Any]:
    document["digest"] = dig({
        k: v for k, v in document.items() if k != "digest"
    })
    _bounded(document)
    return document


def new_author(source: Any) -> dict[str, Any]:
    spec = normalize_survival(source)
    return _seal({
        "schema_version": SCHEMA, "initial_source": spec,
        "source": spec, "source_digest": dig(spec),
        "revision": 0, "edits": [],
    })


def verify_author(payload: Any) -> dict[str, Any]:
    _bounded(payload)
    obj = _object(payload, {
        "schema_version", "initial_source", "source", "source_digest",
        "revision", "edits", "digest",
    }, "survival author document")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported survival author schema")
    edits = obj["edits"]
    if type(edits) is not list or len(edits) > MAX_EDITS:
        raise SceneTravelError("invalid survival author edit journal")
    if type(obj["revision"]) is not int or obj["revision"] != len(edits):
        raise SceneTravelError("survival author revision mismatch")
    initial = normalize_survival(obj["initial_source"])
    if initial != obj["initial_source"]:
        raise SceneTravelError("survival author initial source is not canonical")
    current = initial
    for edit in edits:
        current = _edit(current, edit)
    if (current != obj["source"]
            or dig(current) != obj["source_digest"]
            or obj["digest"] != dig({
                k: v for k, v in obj.items() if k != "digest"
            })):
        raise SceneTravelError("survival author edit replay mismatch")
    return obj


def apply_author(payload: Any, edit: Any, *, expected_digest: str,
                 expected_revision: int) -> dict[str, Any]:
    current = verify_author(payload)
    if (type(expected_digest) is not str
            or expected_digest != current["source_digest"]
            or type(expected_revision) is not int
            or expected_revision != current["revision"]):
        raise SceneTravelError("stale survival source revision or digest")
    if len(current["edits"]) >= MAX_EDITS:
        raise SceneTravelError("survival author edit budget exhausted")
    source = _edit(current["source"], edit)
    result = _seal({
        **current, "source": source, "source_digest": dig(source),
        "revision": current["revision"] + 1,
        "edits": [*current["edits"], edit],
    })
    return verify_author(result)


def preview_author(payload: Any, actions: Any) -> dict[str, Any]:
    document = verify_author(payload)
    session = simulate_survival(document["source"], actions)
    return {
        "schema_version": "skeleton.scene_tile_survival_author_preview.v1",
        "revision": document["revision"],
        "source_digest": document["source_digest"],
        "phase": session["state"]["phase"],
        "health": session["state"]["health"],
        "food": session["state"]["food"],
        "state_digest": session["state_digest"],
        "bundle": export_survival(session),
    }


def solve_author(payload: Any, *, max_states: int = 2048,
                 max_depth: int = 32) -> dict[str, Any]:
    document = verify_author(payload)
    route = solve_survival(
        document["source"], max_states=max_states, max_depth=max_depth,
    )
    return {
        "schema_version": "skeleton.scene_tile_survival_author_route.v1",
        "revision": document["revision"],
        "source_digest": document["source_digest"],
        "route": route,
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-survival-author")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    init = sub.add_parser("new")
    init.add_argument("--source-json", required=True)
    edit = sub.add_parser("edit")
    edit.add_argument("--document-json", required=True)
    edit.add_argument("--edit-json", required=True)
    edit.add_argument("--expected-digest", required=True)
    edit.add_argument("--expected-revision", required=True, type=int)
    verify = sub.add_parser("verify")
    verify.add_argument("--document-json", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--document-json", required=True)
    preview.add_argument("--actions-json", required=True)
    solve = sub.add_parser("solve")
    solve.add_argument("--document-json", required=True)
    solve.add_argument("--max-states", type=int, default=2048)
    solve.add_argument("--max-depth", type=int, default=32)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_survival()
            result = preview_author(new_author(source), actions)
        elif args.command == "new":
            result = new_author(_json(args.source_json))
        elif args.command == "edit":
            result = apply_author(
                _json(args.document_json), _json(args.edit_json),
                expected_digest=args.expected_digest,
                expected_revision=args.expected_revision,
            )
        elif args.command == "verify":
            result = verify_author(_json(args.document_json))
        elif args.command == "preview":
            result = preview_author(
                _json(args.document_json), _json(args.actions_json),
            )
        else:
            result = solve_author(
                _json(args.document_json), max_states=args.max_states,
                max_depth=args.max_depth,
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError,
            UnicodeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
