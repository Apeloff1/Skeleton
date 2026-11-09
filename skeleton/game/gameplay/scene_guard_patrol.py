"""Original offline guard patrols, timed scene exits and deterministic replay.

Guards never grant travel, items or endings. They only block an authored exit
at an authored time. Canonical scene_travel owns every real world transition.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import SaveableGameplayState, dig
from skeleton.game.gameplay.scene_atlas import _strict_json
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance as advance_scene, _id, _object, _action as scene_action,
    new_session, normalize_world, original_demo,
)

SCHEMA = "skeleton.scene_guard_patrol.v1"
BUNDLE = "skeleton.scene_guard_patrol_bundle.v1"
MAX_PATROLS = 8
MAX_TURNS = 64
MAX_BYTES = 2 * 1024 * 1024


def _bounded(raw: Any) -> bytes:
    try:
        encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid patrol JSON") from exc
    if len(encoded) > MAX_BYTES:
        raise SceneTravelError("patrol save exceeds 2 MiB")
    return encoded


def normalize_patrol(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "patrol_id", "world", "guards"},
                  "patrol source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported patrol schema")
    patrol_id = _id(obj["patrol_id"], "patrol id")
    world = normalize_world(obj["world"])
    scenes = {s["id"]: s for s in world["scenes"] if s["ending"] is None}
    items = {p["item_id"] for scene in world["scenes"] for p in scene["pickups"]}
    guards = obj["guards"]
    if type(guards) is not list or not 1 <= len(guards) <= MAX_PATROLS:
        raise SceneTravelError("invalid guard count")
    clean, ids = [], set()
    for raw_guard in guards:
        guard = _object(raw_guard, {"id", "route", "offset", "blocked_exits",
                                    "bypass_item"}, "guard")
        name = _id(guard["id"], "guard id")
        if name in ids:
            raise SceneTravelError("duplicate guard id")
        ids.add(name)
        route = guard["route"]
        if type(route) is not list or not 2 <= len(route) <= 8:
            raise SceneTravelError("guard route length outside 2..8")
        route = [_id(s, "patrol scene") for s in route]
        if len(set(route)) != len(route) or any(s not in scenes for s in route):
            raise SceneTravelError("guard route must use distinct playable scenes")
        for current, target in zip(route, route[1:] + route[:1]):
            if not any(e["to"] == target for e in scenes[current]["exits"]):
                raise SceneTravelError("guard route contains disconnected scenes")
        offset = guard["offset"]
        if type(offset) is not int or not 0 <= offset < len(route):
            raise SceneTravelError("invalid patrol offset")
        bypass = guard["bypass_item"]
        if bypass is not None and (_id(bypass, "bypass item") not in items):
            raise SceneTravelError("guard bypass item is not authored")
        blocked = guard["blocked_exits"]
        if type(blocked) is not list or not 1 <= len(blocked) <= 16:
            raise SceneTravelError("invalid guard blocked exits")
        exits, keys = [], set()
        for raw_exit in blocked:
            edge = _object(raw_exit, {"scene_id", "exit_id"}, "guard exit")
            scene_id = _id(edge["scene_id"], "guard scene")
            exit_id = _id(edge["exit_id"], "guard exit id")
            key = (scene_id, exit_id)
            if (scene_id not in route or key in keys
                    or exit_id not in {e["id"] for e in scenes[scene_id]["exits"]}):
                raise SceneTravelError("guard references invalid or duplicate exit")
            keys.add(key)
            exits.append({"scene_id": scene_id, "exit_id": exit_id})
        clean.append({
            "id": name, "route": route, "offset": offset,
            "blocked_exits": sorted(exits, key=lambda x: (x["scene_id"], x["exit_id"])),
            "bypass_item": bypass,
        })
    spec = {
        "schema_version": SCHEMA, "patrol_id": patrol_id, "world": world,
        "guards": sorted(clean, key=lambda g: g["id"]),
    }
    _bounded(spec)
    return spec


def original_patrol() -> dict[str, Any]:
    world, _ = original_demo()
    gate = next(s for s in world["scenes"] if s["id"] == "gate")
    gate["exits"].append({"id": "back", "to": "quay", "requires_item": None})
    return {
        "schema_version": SCHEMA, "patrol_id": "lantern_watch",
        "world": world, "guards": [{
            "id": "harbor_watch", "route": ["quay", "gate"], "offset": 0,
            "blocked_exits": [
                {"scene_id": "quay", "exit_id": "north"},
                {"scene_id": "gate", "exit_id": "inside"},
            ], "bypass_item": None,
        }],
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_patrol(raw: Any) -> dict[str, Any]:
    source = normalize_patrol(raw)
    state = {"tick": 0, "phase": "active", "scene": new_session(source["world"])}
    return {
        "schema_version": SCHEMA, "source": source, "source_digest": dig(source),
        "state": state, "state_digest": dig(state), "journal": [],
        "save": _save(source, state),
    }


def _action(raw: Any) -> dict[str, str]:
    if type(raw) is dict and raw.get("kind") == "wait":
        _object(raw, {"kind"}, "patrol wait")
        return {"kind": "wait"}
    return scene_action(raw)


def guard_positions(source: dict[str, Any], tick: int) -> list[dict[str, str]]:
    return [
        {"guard_id": g["id"], "scene_id": g["route"][(tick + g["offset"]) % len(g["route"])]}
        for g in source["guards"]
    ]


def _advance_verified(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active" or old["tick"] >= min(
        MAX_TURNS, source["world"]["step_limit"] * 4
    ):
        raise SceneTravelError("patrol terminal or turn budget exceeded")
    action = _action(raw)
    current = old["scene"]
    if action["kind"] == "travel":
        scene_id = current["state"]["scene_id"]
        inventory = set(current["state"]["inventory"])
        for guard in source["guards"]:
            guard_scene = guard["route"][(old["tick"] + guard["offset"]) % len(guard["route"])]
            if (guard_scene == scene_id
                    and {"scene_id": scene_id, "exit_id": action["exit_id"]}
                    in guard["blocked_exits"]
                    and (guard["bypass_item"] is None or guard["bypass_item"] not in inventory)):
                raise SceneTravelError("patrol blocks authored exit")
    scene = current if action["kind"] == "wait" else advance_scene(current, action)
    tick = old["tick"] + 1
    phase = scene["state"]["phase"]
    if phase == "active" and tick >= min(MAX_TURNS, source["world"]["step_limit"] * 4):
        phase = "draw"
    state = {"tick": tick, "phase": phase, "scene": scene}
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    saved = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "save": _save(source, state, session["save"]),
    }
    _bounded(saved)
    return saved


def verify_patrol(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "source", "source_digest",
                        "state", "state_digest", "journal", "save"}, "patrol save")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported patrol save schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_TURNS:
        raise SceneTravelError("invalid patrol journal budget")
    rebuilt = new_patrol(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid patrol event")
        rebuilt = _advance_verified(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("patrol replay event mismatch")
    if rebuilt != obj:
        raise SceneTravelError("patrol save or source lineage mismatch")
    return rebuilt


def advance_patrol(raw: Any, action: Any) -> dict[str, Any]:
    return _advance_verified(verify_patrol(raw), action)


def simulate_patrol(source: Any, actions: Any, *, resume: Any = None) -> dict[str, Any]:
    if type(actions) is not list or len(actions) > MAX_TURNS:
        raise SceneTravelError("invalid patrol action batch")
    session = new_patrol(source) if resume is None else verify_patrol(resume)
    if session["source_digest"] != dig(normalize_patrol(source)):
        raise SceneTravelError("patrol resume source mismatch")
    for action in actions:
        session = _advance_verified(session, action)
    return verify_patrol(session)


def inspect_patrol(raw: Any) -> dict[str, Any]:
    session = verify_patrol(raw)
    state = session["state"]
    result = {
        "schema_version": SCHEMA, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "phase": state["phase"],
        "tick": state["tick"], "scene_id": state["scene"]["state"]["scene_id"],
        "ending": state["scene"]["state"]["ending"],
        "inventory": state["scene"]["state"]["inventory"],
        "guards": guard_positions(session["source"], state["tick"]),
    }
    result["receipt"] = dig(result)
    return result


def export_patrol(raw: Any) -> dict[str, Any]:
    session = verify_patrol(raw)
    bundle = {
        "schema_version": BUNDLE, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _bounded(bundle)
    return bundle


def import_patrol(raw: Any) -> dict[str, Any]:
    _bounded(raw)
    obj = _object(raw, {"schema_version", "source_digest", "state_digest",
                        "session", "checksum"}, "patrol bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported patrol bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("patrol bundle checksum mismatch")
    session = verify_patrol(obj["session"])
    if (obj["source_digest"] != session["source_digest"]
            or obj["state_digest"] != session["state_digest"]):
        raise SceneTravelError("patrol bundle source mismatch")
    return session


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-patrol")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    new = sub.add_parser("new")
    new.add_argument("--source-json", required=True)
    step = sub.add_parser("step")
    step.add_argument("--session-json", required=True)
    step.add_argument("--action-json", required=True)
    for name in ("inspect", "verify", "export"):
        sub.add_parser(name).add_argument("--session-json", required=True)
    imp = sub.add_parser("import")
    imp.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = simulate_patrol(original_patrol(), [
                {"kind": "collect", "pickup_id": "find_key"},
                {"kind": "travel", "exit_id": "north"},
                {"kind": "travel", "exit_id": "inside"},
            ])
        elif args.command == "new":
            result = new_patrol(_strict_json(args.source_json, "patrol source"))
        elif args.command == "import":
            result = import_patrol(_strict_json(args.bundle_json, "patrol bundle"))
        else:
            session = _strict_json(args.session_json, "patrol session")
            if args.command == "step":
                result = advance_patrol(session, _strict_json(args.action_json, "patrol action"))
            elif args.command == "inspect":
                result = inspect_patrol(session)
            elif args.command == "verify":
                result = verify_patrol(session)
            else:
                result = export_patrol(session)
        print(_bounded(result).decode("utf-8"))
        return 0
    except (SceneTravelError, KeyError, ValueError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
