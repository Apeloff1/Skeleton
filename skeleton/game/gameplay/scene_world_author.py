"""Atomic source-bound offline scene/world authoring and playable preview.

Edits are applied to a private copy, then the entire source is revalidated
against the canonical scene runtime. A failed edit publishes no partial world.
Preview executes the production route solver; its bounded inconclusive result
is never mislabeled as unwinnable. Reports are checksums, not signatures.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _json, _limit, _object, normalize_world,
    original_demo,
)
from skeleton.game.gameplay.scene_route_solver import plan_victory

SCHEMA = "skeleton.scene_world_author.v1"
MAX_EDITS = 64
MAX_REPORT_BYTES = 2 * 1024 * 1024


def _encoded_size(value: Any, maximum: int, label: str) -> None:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError(f"invalid {label} JSON") from exc
    if len(raw) > maximum:
        raise SceneTravelError(f"{label} size budget exceeded")


def _find(world: dict[str, Any], scene_id: Any) -> dict[str, Any]:
    target = _id(scene_id, "scene_id")
    for scene in world["scenes"]:
        if scene["id"] == target:
            return scene
    raise SceneTravelError("authored scene does not exist")


def _apply(world: dict[str, Any], raw: Any) -> None:
    """One exact-field edit on an isolated working copy; no I/O or code eval."""
    if type(raw) is not dict or type(raw.get("kind")) is not str:
        raise SceneTravelError("invalid world edit")
    kind = raw["kind"]
    if kind == "add_scene":
        _object(raw, {"kind", "scene"}, "add_scene")
        scene = raw["scene"]
        _object(scene, {"id", "ending", "pickups", "exits"}, "new scene")
        _id(scene["id"], "scene_id")
        if any(item["id"] == scene["id"] for item in world["scenes"]):
            raise SceneTravelError("duplicate scene_id")
        world["scenes"].append(deepcopy(scene))
        return
    if kind == "remove_scene":
        _object(raw, {"kind", "scene_id"}, "remove_scene")
        scene = _find(world, raw["scene_id"])
        if scene["id"] == world["start_scene"]:
            raise SceneTravelError("cannot remove start scene")
        world["scenes"].remove(scene)
        return
    if kind == "set_start":
        _object(raw, {"kind", "scene_id"}, "set_start")
        world["start_scene"] = _find(world, raw["scene_id"])["id"]
        return
    if kind == "set_step_limit":
        _object(raw, {"kind", "step_limit"}, "set_step_limit")
        world["step_limit"] = _limit(raw["step_limit"], "step_limit", 1, 512)
        return
    if kind == "set_ending":
        _object(raw, {"kind", "scene_id", "ending"}, "set_ending")
        scene = _find(world, raw["scene_id"])
        ending = raw["ending"]
        if ending is not None and ending not in ("victory", "failure"):
            raise SceneTravelError("invalid ending")
        scene["ending"] = ending
        return
    if kind in ("add_exit", "remove_exit", "add_pickup", "remove_pickup"):
        field = "exits" if kind.endswith("exit") else "pickups"
        scene = _find(world, raw.get("scene_id"))
        if kind.startswith("add_"):
            member = "exit" if field == "exits" else "pickup"
            _object(raw, {"kind", "scene_id", member}, kind)
            data = raw[member]
            keys = (
                {"id", "to", "requires_item"} if field == "exits"
                else {"id", "item_id"}
            )
            _object(data, keys, member)
            member_id = _id(data["id"], "member_id")
            if any(item["id"] == member_id for item in scene[field]):
                raise SceneTravelError("duplicate authored interaction")
            scene[field].append(deepcopy(data))
        else:
            member = "exit_id" if field == "exits" else "pickup_id"
            _object(raw, {"kind", "scene_id", member}, kind)
            member_id = _id(raw[member], "member_id")
            matches = [item for item in scene[field] if item["id"] == member_id]
            if len(matches) != 1:
                raise SceneTravelError("interaction to remove does not exist")
            scene[field].remove(matches[0])
        return
    raise SceneTravelError("unsupported world author operation")


def _patch(source: Any, edits: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    _encoded_size(source, 131072, "world source")
    _encoded_size(edits, 131072, "world edits")
    before = normalize_world(source)
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS:
        raise SceneTravelError("world edit count outside 1..64")
    working = deepcopy(before)
    for edit in edits:
        _apply(working, edit)
    after = normalize_world(working)
    if before == after:
        raise SceneTravelError("world edit is a no-op")
    return before, after


def author_world(
    source: Any, edits: Any, *, max_states: int = 256,
    max_depth: int = 64,
) -> dict[str, Any]:
    """Produce a fully validated source revision with a canonical playtest."""
    if type(max_states) is not int or not 1 <= max_states <= 4096:
        raise SceneTravelError("invalid preview state budget")
    if type(max_depth) is not int or not 1 <= max_depth <= 512:
        raise SceneTravelError("invalid preview depth budget")
    before, after = _patch(source, edits)
    preview = plan_victory(after, max_states=max_states, max_depth=max_depth)
    if preview["source_digest"] != dig(after):
        raise SceneTravelError("preview source identity mismatch")
    result = {
        "schema_version": SCHEMA,
        "before_source": before,
        "after_source": after,
        "before_digest": dig(before),
        "after_digest": dig(after),
        "edits": deepcopy(edits),
        "edits_digest": dig(edits),
        "edit_count": len(edits),
        "preview_max_states": max_states,
        "preview_max_depth": max_depth,
        "preview": preview,
    }
    result["checksum"] = dig(result)
    _encoded_size(result, MAX_REPORT_BYTES, "world edit report")
    return result


def verify_authoring_report(payload: Any) -> dict[str, Any]:
    """Reapply edits and recompute route preview; reject changed source."""
    _encoded_size(payload, MAX_REPORT_BYTES, "world edit report")
    keys = {
        "schema_version", "before_source", "after_source", "before_digest",
        "after_digest", "edits", "edits_digest", "edit_count",
        "preview_max_states", "preview_max_depth", "preview", "checksum",
    }
    report = _object(payload, keys, "world edit report")
    if report["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported world author report schema")
    expected = author_world(
        report["before_source"], report["edits"],
        max_states=report["preview_max_states"],
        max_depth=report["preview_max_depth"],
    )
    if report != expected:
        raise SceneTravelError("world author replay or checksum mismatch")
    return expected


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton scene-author",
        description="Atomic offline scene authoring and canonical route playtest",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Add an original reachable scene to demo world")
    edit = sub.add_parser("edit", help="Apply an atomic source edit batch")
    edit.add_argument("--world-json", required=True)
    edit.add_argument("--edits-json", required=True)
    edit.add_argument("--max-states", type=int, default=256)
    edit.add_argument("--max-depth", type=int, default=64)
    verify = sub.add_parser("verify", help="Reapply and verify a source edit receipt")
    verify.add_argument("--report-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            world, _ = original_demo()
            edits = [
                {"kind": "add_scene", "scene": {
                    "id": "lighthouse", "ending": None, "pickups": [],
                    "exits": [{"id": "back", "to": "quay", "requires_item": None}],
                }},
                {"kind": "add_exit", "scene_id": "quay", "exit": {
                    "id": "east", "to": "lighthouse", "requires_item": None,
                }},
            ]
            result = author_world(world, edits)
        elif args.command == "edit":
            result = author_world(
                _json(args.world_json, "world"),
                _json(args.edits_json, "edits"),
                max_states=args.max_states, max_depth=args.max_depth,
            )
        else:
            result = verify_authoring_report(
                _json(args.report_json, "author report", max_bytes=MAX_REPORT_BYTES)
            )
        print(json.dumps(result, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
