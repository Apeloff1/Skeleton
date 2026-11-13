"""Transactional source authoring and playable preview for offline convoy escorts.

Edits are replayed from a source-bound genesis; no client-supplied balance,
supply, destination or reward can be silently accepted as a gameplay grant.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_escort import (
    MAX_BYTES, _bounded, demo_actions, export_escort, normalize_escort_source,
    original_escort, simulate_escort,
)
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _limit, _object

SCHEMA = "skeleton.scene_escort_author.v1"
MAX_EDITS = 64


def _edit(source: dict[str, Any], raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid escort source edit")
    kind = raw.get("kind")
    spec = {**source, "hazards": [dict(x) for x in source["hazards"]],
            "supply_pickups": list(source["supply_pickups"])}
    if kind in ("set_integrity", "set_travel_damage", "set_reward"):
        _object(raw, {"kind", "value"}, "escort scalar edit")
        field, low, high = {
            "set_integrity": ("max_integrity", 1, 100),
            "set_travel_damage": ("travel_damage", 0, 9),
            "set_reward": ("delivery_reward", 0, 10000),
        }[kind]
        spec[field] = _limit(raw["value"], field, low, high)
    elif kind == "set_destination":
        _object(raw, {"kind", "scene_id"}, "escort destination edit")
        spec["destination_scene"] = _id(raw["scene_id"], "destination scene")
    elif kind == "set_hazard":
        _object(raw, {"kind", "scene_id", "damage"}, "escort hazard edit")
        scene = _id(raw["scene_id"], "hazard scene")
        damage = _limit(raw["damage"], "hazard damage", 0, 9)
        spec["hazards"] = [x for x in spec["hazards"] if x["scene_id"] != scene]
        spec["hazards"].append({"scene_id": scene, "damage": damage})
    elif kind == "remove_hazard":
        _object(raw, {"kind", "scene_id"}, "escort hazard removal")
        scene = _id(raw["scene_id"], "hazard scene")
        if not any(x["scene_id"] == scene for x in spec["hazards"]):
            raise SceneTravelError("escort hazard not authored")
        spec["hazards"] = [x for x in spec["hazards"] if x["scene_id"] != scene]
    elif kind in ("add_supply", "remove_supply"):
        _object(raw, {"kind", "pickup"}, "escort supply edit")
        pickup = _id(raw["pickup"], "supply pickup")
        if kind == "add_supply":
            if pickup in spec["supply_pickups"]:
                raise SceneTravelError("escort supply already authored")
            spec["supply_pickups"].append(pickup)
        else:
            if pickup not in spec["supply_pickups"]:
                raise SceneTravelError("escort supply not authored")
            spec["supply_pickups"].remove(pickup)
    else:
        raise SceneTravelError("unsupported escort source edit")
    return normalize_escort_source(spec)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    value["digest"] = dig({k: v for k, v in value.items() if k != "digest"})
    _bounded(value)
    return value


def new_author(source: Any) -> dict[str, Any]:
    spec = normalize_escort_source(source)
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
    }, "escort author document")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported escort author schema")
    edits = obj["edits"]
    if type(edits) is not list or len(edits) > MAX_EDITS:
        raise SceneTravelError("escort author edit budget exceeded")
    if type(obj["revision"]) is not int or obj["revision"] != len(edits):
        raise SceneTravelError("escort author revision mismatch")
    source = normalize_escort_source(obj["initial_source"])
    if source != obj["initial_source"]:
        raise SceneTravelError("escort author initial source not canonical")
    for edit in edits:
        source = _edit(source, edit)
    if (source != obj["source"] or dig(source) != obj["source_digest"]
            or obj["digest"] != dig({k: v for k, v in obj.items() if k != "digest"})):
        raise SceneTravelError("escort author source or edit replay mismatch")
    return obj


def apply_author(payload: Any, edit: Any, *, expected_digest: str,
                 expected_revision: int) -> dict[str, Any]:
    current = verify_author(payload)
    if (type(expected_digest) is not str
            or expected_digest != current["source_digest"]
            or type(expected_revision) is not int
            or expected_revision != current["revision"]):
        raise SceneTravelError("stale escort source revision or digest")
    if len(current["edits"]) >= MAX_EDITS:
        raise SceneTravelError("escort author edit budget exceeded")
    source = _edit(current["source"], edit)
    updated = _seal({
        **current, "source": source, "source_digest": dig(source),
        "revision": current["revision"] + 1,
        "edits": [*current["edits"], edit],
    })
    return verify_author(updated)


def preview_author(payload: Any, actions: Any) -> dict[str, Any]:
    doc = verify_author(payload)
    session = simulate_escort(doc["source"], actions)
    portable = export_escort(session)
    return {
        "schema_version": "skeleton.scene_escort_author_preview.v1",
        "source_digest": doc["source_digest"], "revision": doc["revision"],
        "phase": session["state"]["phase"], "reward": session["state"]["reward"],
        "integrity": session["state"]["integrity"],
        "state_digest": session["state_digest"], "bundle": portable,
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-escort-author")
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
    args = parser.parse_args(list(argv))
    try:
        parse = lambda raw: _strict_json(raw, "escort author JSON", max_bytes=MAX_BYTES)
        if args.command == "demo":
            result = preview_author(new_author(original_escort()), demo_actions())
        elif args.command == "new":
            result = new_author(parse(args.source_json))
        elif args.command == "edit":
            result = apply_author(
                parse(args.document_json), parse(args.edit_json),
                expected_digest=args.expected_digest,
                expected_revision=args.expected_revision,
            )
        elif args.command == "verify":
            result = verify_author(parse(args.document_json))
        else:
            result = preview_author(parse(args.document_json), parse(args.actions_json))
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
