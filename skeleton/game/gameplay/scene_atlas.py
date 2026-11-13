"""Fog-of-war scene atlas derived exclusively from canonical offline replay.

The atlas exposes only visited rooms and their exits. It never invents paths,
unlocks authored item gates, mutates source or trusts client-supplied map data.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance, _id, _object,
    new_session, original_demo, simulate, verify_session,
)

SCHEMA = "skeleton.scene_atlas.v1"
BUNDLE_SCHEMA = "skeleton.scene_atlas_bundle.v1"
MAX_BUNDLE_BYTES = 2 * 1024 * 1024


def _size(value: Any) -> None:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid atlas JSON") from exc
    if len(encoded) > MAX_BUNDLE_BYTES:
        raise SceneTravelError("atlas export exceeds bounded size")


def _strict_json(text: str, label: str, *, max_bytes: int = MAX_BUNDLE_BYTES) -> Any:
    """Reject duplicate keys, nonfinite numbers and oversized untrusted input."""
    if type(text) is not str:
        raise SceneTravelError(f"invalid {label} JSON")
    try:
        if len(text.encode("utf-8")) > max_bytes:
            raise SceneTravelError(f"{label} exceeds input budget")
        def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON key")
                result[key] = value
            return result

        def reject_nonfinite(value: str) -> None:
            raise ValueError("nonfinite JSON value")

        return json.loads(
            text, object_pairs_hook=unique_pairs,
            parse_constant=reject_nonfinite,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError(f"invalid {label} JSON") from exc


def inspect_atlas(payload: Any) -> dict[str, Any]:
    """Derive explored rooms, visible interactions and replayed route history."""
    session = verify_session(payload)
    spec = session["world"]
    state = session["state"]
    visited = set(state["visited"])
    collected = set(state["collected"])
    items = set(state["inventory"])
    rooms = []
    for scene in spec["scenes"]:
        if scene["id"] not in visited:
            continue
        rooms.append({
            "scene_id": scene["id"],
            "ending": scene["ending"],
            "current": scene["id"] == state["scene_id"],
            "pickups": [{
                "pickup_id": pickup["id"],
                "item_id": pickup["item_id"],
                "collected": scene["id"] + ":" + pickup["id"] in collected,
            } for pickup in scene["pickups"]],
            "exits": [{
                "exit_id": edge["id"],
                "to": edge["to"],
                "destination_discovered": edge["to"] in visited,
                "requires_item": edge["requires_item"],
                "unlocked": (
                    edge["requires_item"] is None
                    or edge["requires_item"] in items
                ),
            } for edge in scene["exits"]],
        })
    cursor = new_session(spec)
    history = []
    for event in session["journal"]:
        before = cursor["state"]
        cursor = _advance(cursor, event["action"])
        after = cursor["state"]
        history.append({
            "turn": event["sequence"],
            "action": event["action"],
            "from": before["scene_id"],
            "to": after["scene_id"],
            "new_items": sorted(
                set(after["inventory"]) - set(before["inventory"])
            ),
            "phase": after["phase"],
            "receipt": event["receipt"],
        })
    if cursor != session:
        raise SceneTravelError("atlas route history differs from verified save")
    return {
        "schema_version": SCHEMA,
        "world_id": spec["world_id"],
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "event_bus_digest": session["event_bus_digest"],
        "current_scene": state["scene_id"],
        "phase": state["phase"],
        "ending": state["ending"],
        "known_scene_count": len(rooms),
        "total_authored_scene_count": len(spec["scenes"]),
        "inventory": sorted(items),
        "rooms": rooms,
        "history": history,
    }


def route_known(payload: Any, target_scene: Any) -> dict[str, Any]:
    """Shortest legal path through discovered rooms, respecting held item gates.

    Undiscovered destinations are never used as intermediate nodes. The route
    is a suggestion from a verified save, not a mutation or travel grant.
    """
    atlas = inspect_atlas(payload)
    target = _id(target_scene, "target_scene")
    known = {room["scene_id"]: room for room in atlas["rooms"]}
    if target not in known:
        raise SceneTravelError("destination has not been discovered")
    origin = atlas["current_scene"]
    frontier = deque([(origin, [])])
    seen = {origin}
    path: list[dict[str, str]] | None = None
    while frontier:
        current, commands = frontier.popleft()
        if current == target:
            path = commands
            break
        for edge in known[current]["exits"]:
            next_room = edge["to"]
            if (
                not edge["unlocked"]
                or next_room not in known
                or next_room in seen
            ):
                continue
            seen.add(next_room)
            frontier.append((next_room, [
                *commands,
                {"kind": "travel", "exit_id": edge["exit_id"],
                 "from": current, "to": next_room},
            ]))
    result = {
        "schema_version": SCHEMA,
        "source_digest": atlas["source_digest"],
        "state_digest": atlas["state_digest"],
        "from": origin,
        "target": target,
        "reachable": path is not None,
        "steps": path,
        "explored_nodes": len(seen),
    }
    result["receipt"] = dig(result)
    return result


def compare_atlases(left: Any, right: Any) -> dict[str, Any]:
    """Compare two valid playthroughs of the exact same authored world."""
    a = verify_session(left)
    b = verify_session(right)
    if a["source_digest"] != b["source_digest"]:
        raise SceneTravelError("atlas comparison needs identical authored world")
    common = 0
    while (
        common < min(len(a["journal"]), len(b["journal"]))
        and a["journal"][common] == b["journal"][common]
    ):
        common += 1
    relation = (
        "identical" if a == b else
        "prefix" if common in (len(a["journal"]), len(b["journal"]))
        else "divergent"
    )
    result = {
        "schema_version": SCHEMA,
        "source_digest": a["source_digest"],
        "relationship": relation,
        "common_turns": common,
        "left": {
            "turns": len(a["journal"]),
            "state_digest": a["state_digest"],
            "current_scene": a["state"]["scene_id"],
            "visited": sorted(a["state"]["visited"]),
            "inventory": sorted(a["state"]["inventory"]),
            "ending": a["state"]["ending"],
        },
        "right": {
            "turns": len(b["journal"]),
            "state_digest": b["state_digest"],
            "current_scene": b["state"]["scene_id"],
            "visited": sorted(b["state"]["visited"]),
            "inventory": sorted(b["state"]["inventory"]),
            "ending": b["state"]["ending"],
        },
        "newly_visited_on_right": sorted(
            set(b["state"]["visited"]) - set(a["state"]["visited"])
        ),
        "new_items_on_right": sorted(
            set(b["state"]["inventory"]) - set(a["state"]["inventory"])
        ),
    }
    result["receipt"] = dig(result)
    return result


def export_atlas(payload: Any) -> dict[str, Any]:
    session = verify_session(payload)
    atlas = inspect_atlas(session)
    record = {
        "schema_version": BUNDLE_SCHEMA,
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "session": session,
        "atlas": atlas,
    }
    record["checksum"] = dig(record)
    _size(record)
    return record


def import_atlas(raw: Any) -> dict[str, Any]:
    """Replay-verify a portable atlas; never trust its map or checksum alone."""
    _size(raw)
    obj = _object(raw, {
        "schema_version", "source_digest", "state_digest",
        "session", "atlas", "checksum",
    }, "atlas bundle")
    if obj["schema_version"] != BUNDLE_SCHEMA:
        raise SceneTravelError("unsupported atlas bundle schema")
    if type(obj["checksum"]) is not str or len(obj["checksum"]) != 64:
        raise SceneTravelError("invalid atlas checksum")
    if dig({key: value for key, value in obj.items() if key != "checksum"}) != obj["checksum"]:
        raise SceneTravelError("atlas checksum mismatch")
    session = verify_session(obj["session"])
    if (
        obj["source_digest"] != session["source_digest"]
        or obj["state_digest"] != session["state_digest"]
        or obj["atlas"] != inspect_atlas(session)
    ):
        raise SceneTravelError("atlas source or replay mismatch")
    return session


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-atlas")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Explore original demo and export replay-verified atlas")
    for command in ("inspect", "export"):
        cmd = sub.add_parser(command)
        cmd.add_argument("--session-json", required=True)
    route = sub.add_parser("route")
    route.add_argument("--session-json", required=True)
    route.add_argument("--target-scene", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--left-json", required=True)
    compare.add_argument("--right-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            world, actions = original_demo()
            result = export_atlas(simulate(world, actions))
        elif args.command == "inspect":
            result = inspect_atlas(_strict_json(args.session_json, "session", max_bytes=MAX_BUNDLE_BYTES))
        elif args.command == "export":
            result = export_atlas(_strict_json(args.session_json, "session", max_bytes=MAX_BUNDLE_BYTES))
        elif args.command == "route":
            result = route_known(
                _strict_json(args.session_json, "session", max_bytes=MAX_BUNDLE_BYTES),
                args.target_scene,
            )
        elif args.command == "compare":
            result = compare_atlases(
                _strict_json(args.left_json, "left session", max_bytes=MAX_BUNDLE_BYTES),
                _strict_json(args.right_json, "right session", max_bytes=MAX_BUNDLE_BYTES),
            )
        else:
            result = import_atlas(_strict_json(args.bundle_json, "atlas bundle", max_bytes=MAX_BUNDLE_BYTES))
        _size(result)
        print(json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return 0
    except (SceneTravelError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
