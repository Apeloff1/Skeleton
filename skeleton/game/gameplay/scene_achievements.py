"""Replay-derived offline achievements for canonical authored scene worlds.

Achievements are observations over verified source-bound gameplay, never
client-submitted rewards. Export includes a full replay witness; checksum is
integrity only and is not proof of a trusted author.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_travel import (
    MAX_STEPS, SceneTravelError, _advance, _id, _limit, _object,
    new_session, original_demo, simulate, verify_session,
)

SCHEMA = "skeleton.scene_achievements.v1"
BUNDLE_SCHEMA = "skeleton.scene_achievements_bundle.v1"
MAX_RULES = 32
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def normalize_rules(raw: Any, world: dict[str, Any],
                    source_digest: str) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "world_id", "source_digest", "rules"},
                  "achievement catalog")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported achievement catalog")
    if obj["world_id"] != world["world_id"] or obj["source_digest"] != source_digest:
        raise SceneTravelError("achievement catalog source mismatch")
    if type(obj["source_digest"]) is not str or DIGEST.fullmatch(obj["source_digest"]) is None:
        raise SceneTravelError("invalid achievement source digest")
    entries = obj["rules"]
    if type(entries) is not list or not 1 <= len(entries) <= MAX_RULES:
        raise SceneTravelError("achievement rule count outside 1..32")
    scenes = {scene["id"] for scene in world["scenes"]}
    items = {p["item_id"] for scene in world["scenes"] for p in scene["pickups"]}
    seen = set()
    result = []
    for raw_rule in entries:
        rule = _object(raw_rule, {"id", "kind", "target"}, "achievement rule")
        rule_id = _id(rule["id"], "achievement id")
        if rule_id in seen:
            raise SceneTravelError("duplicate achievement id")
        seen.add(rule_id)
        kind = rule["kind"]
        if type(kind) is not str or kind not in (
            "visit_scene", "collect_item", "ending", "finish_within",
        ):
            raise SceneTravelError("unknown achievement condition")
        target = rule["target"]
        if kind == "finish_within":
            target = _limit(target, "finish_within", 1, MAX_STEPS)
        else:
            target = _id(target, "achievement target")
            if (kind == "visit_scene" and target not in scenes
                    or kind == "collect_item" and target not in items
                    or kind == "ending" and target not in ("victory", "failure")):
                raise SceneTravelError("achievement target absent from authored world")
        result.append({"id": rule_id, "kind": kind, "target": target})
    return {"schema_version": SCHEMA, "world_id": world["world_id"],
            "source_digest": source_digest, "rules": sorted(result, key=lambda r: r["id"])}


def _qualifies(rule: dict[str, Any], state: dict[str, Any]) -> bool:
    kind, target = rule["kind"], rule["target"]
    if kind == "visit_scene":
        return target in state["visited"]
    if kind == "collect_item":
        return target in state["inventory"]
    if kind == "ending":
        return state["ending"] == target
    return state["phase"] in ("won", "lost") and state["tick"] <= target


def inspect_achievements(session: Any, catalog: Any) -> dict[str, Any]:
    verified = verify_session(session)
    spec = normalize_rules(catalog, verified["world"], verified["source_digest"])
    cursor = new_session(verified["world"])
    unlocked = {}
    # Initial location can legitimately unlock a visit achievement at tick 0.
    for event in [None, *verified["journal"]]:
        if event is not None:
            cursor = _advance(cursor, event["action"])
        for rule in spec["rules"]:
            if rule["id"] not in unlocked and _qualifies(rule, cursor["state"]):
                unlocked[rule["id"]] = {
                    "tick": cursor["state"]["tick"],
                    "state_digest": cursor["state_digest"],
                    "action_receipt": event["receipt"] if event is not None else None,
                }
    if cursor != verified:
        raise SceneTravelError("achievement replay mismatch")
    achievements = [
        {"id": rule["id"], "kind": rule["kind"], "target": rule["target"],
         "earned": rule["id"] in unlocked, "witness": unlocked.get(rule["id"])}
        for rule in spec["rules"]
    ]
    record = {"schema_version": SCHEMA, "world_id": spec["world_id"],
              "source_digest": verified["source_digest"],
              "state_digest": verified["state_digest"],
              "event_bus_digest": verified["event_bus_digest"],
              "catalog_digest": dig(spec), "achievements": achievements,
              "earned_count": len(unlocked), "total_count": len(achievements)}
    return {**record, "receipt": dig(record)}


def _size(payload: Any) -> None:
    try:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         allow_nan=False, ensure_ascii=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid achievement JSON") from exc
    if len(raw) > MAX_BUNDLE_BYTES:
        raise SceneTravelError("achievement bundle exceeds 2 MiB")


def export_achievements(session: Any, catalog: Any) -> dict[str, Any]:
    verified = verify_session(session)
    spec = normalize_rules(catalog, verified["world"], verified["source_digest"])
    report = inspect_achievements(verified, spec)
    record = {"schema_version": BUNDLE_SCHEMA, "session": verified,
              "catalog": spec, "report": report,
              "source_digest": verified["source_digest"],
              "state_digest": verified["state_digest"]}
    bundle = {**record, "checksum": dig(record)}
    _size(bundle)
    return bundle


def import_achievements(payload: Any) -> dict[str, Any]:
    _size(payload)
    obj = _object(payload, {"schema_version", "session", "catalog", "report",
                            "source_digest", "state_digest", "checksum"},
                  "achievement bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA:
        raise SceneTravelError("unsupported achievement bundle")
    if type(obj["checksum"]) is not str or DIGEST.fullmatch(obj["checksum"]) is None:
        raise SceneTravelError("invalid achievement checksum")
    if dig({key: value for key, value in obj.items() if key != "checksum"}) != obj["checksum"]:
        raise SceneTravelError("achievement checksum mismatch")
    session = verify_session(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]
            or inspect_achievements(session, obj["catalog"]) != obj["report"]):
        raise SceneTravelError("achievement replay or identity mismatch")
    return obj["report"]


def original_catalog(world: Any) -> dict[str, Any]:
    session = new_session(world)
    return {"schema_version": SCHEMA, "world_id": session["world"]["world_id"],
            "source_digest": session["source_digest"], "rules": [
                {"id": "first_steps", "kind": "visit_scene", "target": "quay"},
                {"id": "key_keeper", "kind": "collect_item", "target": "brass_key"},
                {"id": "safe_arrival", "kind": "ending", "target": "victory"},
                {"id": "swift_arrival", "kind": "finish_within", "target": 3},
                {"id": "sinkhole_warning", "kind": "ending", "target": "failure"},
            ]}


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-achievements")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Original scene exploration and earned milestones")
    for name in ("inspect", "export"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--session-json", required=True)
        cmd.add_argument("--catalog-json", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            world, actions = original_demo()
            result = export_achievements(simulate(world, actions), original_catalog(world))
        elif args.command == "import":
            result = import_achievements(_strict_json(args.bundle_json, "bundle"))
        else:
            session = _strict_json(args.session_json, "session")
            catalog = _strict_json(args.catalog_json, "catalog")
            result = (export_achievements(session, catalog)
                      if args.command == "export"
                      else inspect_achievements(session, catalog))
        _size(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
