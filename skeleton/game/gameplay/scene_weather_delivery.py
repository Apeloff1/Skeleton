"""Replay-proven weather caravan deliveries with earned economic consequences.

The canonical weather engine owns every movement, collision, inventory pickup
and clock tick. Delivery rewards are only derived from verified arrivals with
the required item before an authored deadline; client claims are never trusted.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import SceneTravelError, _id, _json, _limit, _object
from skeleton.game.gameplay.scene_weather import (
    _export, new_session as new_weather, normalize_weather,
    original_weather_demo, resume_session as resume_weather,
)

SCHEMA = "skeleton.weather_deliveries.v1"
PACKAGE_SCHEMA = "skeleton.weather_deliveries_package.v1"
MAX_DELIVERIES = 16
MAX_REWARD = 10000
MAX_TOTAL_REWARD = 100000


def normalize_deliveries(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "weather", "deliveries"},
                  "delivery source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported delivery schema")
    weather = normalize_weather(obj["weather"])
    entries = obj["deliveries"]
    if type(entries) is not list or not 1 <= len(entries) <= MAX_DELIVERIES:
        raise SceneTravelError("invalid delivery count")
    scene_ids = {scene["id"] for scene in weather["world"]["scenes"]}
    items = {
        pickup["item_id"]
        for scene in weather["world"]["scenes"] for pickup in scene["pickups"]
    }
    ids: set[str] = set()
    deliveries: list[dict[str, Any]] = []
    total = 0
    for raw_entry in entries:
        entry = _object(raw_entry, {
            "delivery_id", "destination_scene", "required_item",
            "deadline", "reward", "requires",
        }, "delivery")
        delivery_id = _id(entry["delivery_id"], "delivery_id")
        destination = _id(entry["destination_scene"], "destination_scene")
        item = _id(entry["required_item"], "required_item")
        if delivery_id in ids:
            raise SceneTravelError("duplicate delivery identity")
        if destination not in scene_ids:
            raise SceneTravelError("unknown delivery destination")
        if item not in items:
            raise SceneTravelError("delivery item is never authored")
        deadline = _limit(entry["deadline"], "delivery deadline", 1,
                          weather["world"]["step_limit"])
        reward = _limit(entry["reward"], "delivery reward", 1, MAX_REWARD)
        total += reward
        if total > MAX_TOTAL_REWARD:
            raise SceneTravelError("delivery reward budget exceeded")
        dependencies = entry["requires"]
        if (type(dependencies) is not list or len(dependencies) > MAX_DELIVERIES):
            raise SceneTravelError("invalid delivery dependencies")
        checked: list[str] = []
        for value in dependencies:
            dependency = _id(value, "required delivery")
            if dependency not in ids or dependency in checked:
                raise SceneTravelError("duplicate, unknown or forward delivery dependency")
            checked.append(dependency)
        ids.add(delivery_id)
        deliveries.append({
            "delivery_id": delivery_id, "destination_scene": destination,
            "required_item": item, "deadline": deadline,
            "reward": reward, "requires": checked,
        })
    result = {"schema_version": SCHEMA, "weather": weather,
              "deliveries": deliveries}
    _export(result)
    return result


def _statuses(journal: list[dict[str, Any]]) -> dict[str, str]:
    return {
        event["delivery_id"]: event["status"]
        for step in journal for event in step["changes"]
    }


def _checkpoint(source: dict[str, Any], weather: dict[str, Any],
                state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_version": "skeleton.weather_deliveries_save.v1",
        "source_digest": dig(source), "state_digest": dig(state),
        "weather_save_digest": dig(weather["save"]),
        "parent_digest": None if parent is None else dig(parent),
        "tick": len(state["journal"]),
    }


def _snapshot(source: dict[str, Any], weather: dict[str, Any],
              state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "weather_session": weather,
        "state": state, "state_digest": dig(state),
        "save": _checkpoint(source, weather, state, parent),
    }
    _export(result)
    return result


def new_deliveries(source: Any) -> dict[str, Any]:
    spec = normalize_deliveries(source)
    weather = new_weather(spec["weather"])
    state = {"phase": "active", "earned": 0, "journal": []}
    return _snapshot(spec, weather, state, None)


def _advance(snapshot: dict[str, Any], action: Any) -> dict[str, Any]:
    if snapshot["state"]["phase"] != "active":
        raise SceneTravelError("delivery journey already terminal")
    weather = resume_weather(snapshot["weather_session"], [action])
    old = snapshot["state"]
    statuses = _statuses(old["journal"])
    scene = weather["state"]["scene"]["state"]
    scene_id = scene["scene_id"]
    inventory = set(scene["inventory"])
    tick = weather["state"]["tick"]
    changes: list[dict[str, Any]] = []
    earned = old["earned"]
    for delivery in snapshot["source"]["deliveries"]:
        delivery_id = delivery["delivery_id"]
        if delivery_id in statuses:
            continue
        if tick > delivery["deadline"]:
            status = "expired"
        elif (scene_id == delivery["destination_scene"]
              and delivery["required_item"] in inventory
              and all(statuses.get(dep) == "delivered"
                      for dep in delivery["requires"])):
            status = "delivered"
        else:
            continue
        reward = delivery["reward"] if status == "delivered" else 0
        earned += reward
        if earned > MAX_TOTAL_REWARD:
            raise SceneTravelError("delivery reward overflow")
        statuses[delivery_id] = status
        changes.append({
            "delivery_id": delivery_id, "status": status, "reward": reward,
        })
    if all(statuses.get(d["delivery_id"]) == "delivered"
           for d in snapshot["source"]["deliveries"]):
        phase = "won"
    elif weather["state"]["phase"] != "active":
        phase = weather["state"]["phase"]
    elif len(statuses) == len(snapshot["source"]["deliveries"]):
        phase = "lost"
    else:
        phase = "active"
    step = {
        "action": weather["journal"][-1]["action"],
        "weather_state_digest": weather["state_digest"],
        "changes": changes, "earned_after": earned,
    }
    state = {
        "phase": phase, "earned": earned,
        "journal": [*old["journal"], step],
    }
    return _snapshot(snapshot["source"], weather, state, snapshot["save"])


def verify_deliveries(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "weather_session",
        "state", "state_digest", "save",
    }, "delivery session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported delivery save schema")
    _export(obj)
    journal = obj["state"].get("journal") if type(obj["state"]) is dict else None
    if type(journal) is not list:
        raise SceneTravelError("invalid delivery journal")
    rebuilt = new_deliveries(obj["source"])
    if len(journal) > rebuilt["source"]["weather"]["world"]["step_limit"]:
        raise SceneTravelError("delivery journal exceeds step budget")
    for step in journal:
        if type(step) is not dict or "action" not in step:
            raise SceneTravelError("malformed delivery journal")
        rebuilt = _advance(rebuilt, step["action"])
    if rebuilt != obj:
        raise SceneTravelError("delivery replay or checkpoint mismatch")
    return rebuilt


def advance_deliveries(raw: Any, action: Any) -> dict[str, Any]:
    return _advance(verify_deliveries(raw), action)


def resume_deliveries(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_deliveries(raw)
    if type(actions) is not list or (
        len(session["state"]["journal"]) + len(actions)
        > session["source"]["weather"]["world"]["step_limit"]
    ):
        raise SceneTravelError("delivery action batch exceeds step budget")
    for action in actions:
        session = _advance(session, action)
    return verify_deliveries(session)


def delivery_summary(raw: Any) -> dict[str, Any]:
    session = verify_deliveries(raw)
    statuses = _statuses(session["state"]["journal"])
    phase = session["state"]["phase"]
    return {
        "schema_version": SCHEMA, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "phase": phase,
        "earned": session["state"]["earned"],
        "deliveries": [{
            "delivery_id": entry["delivery_id"],
            "status": statuses.get(entry["delivery_id"],
                                   "pending" if phase == "active" else "unreachable"),
        } for entry in session["source"]["deliveries"]],
    }


def package_deliveries(raw: Any) -> dict[str, Any]:
    snapshot = verify_deliveries(raw)
    manifest = {
        "source_digest": snapshot["source_digest"],
        "state_digest": snapshot["state_digest"],
        "weather_save_digest": dig(snapshot["weather_session"]["save"]),
        "phase": snapshot["state"]["phase"],
        "earned": snapshot["state"]["earned"],
        "tick": len(snapshot["state"]["journal"]),
    }
    result = {"schema_version": PACKAGE_SCHEMA,
              "manifest": manifest, "snapshot": snapshot}
    result["digest"] = dig(result)
    _export(result)
    return result


def verify_delivery_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "manifest", "snapshot", "digest"},
                  "delivery package")
    if obj["schema_version"] != PACKAGE_SCHEMA:
        raise SceneTravelError("unsupported delivery package schema")
    _export(obj)
    expected = package_deliveries(obj["snapshot"])
    if expected != obj:
        raise SceneTravelError("delivery package integrity or replay mismatch")
    return expected


def original_deliveries() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    weather, actions = original_weather_demo()
    source = {
        "schema_version": SCHEMA, "weather": weather,
        "deliveries": [
            {"delivery_id": "gate_supply", "destination_scene": "gate",
             "required_item": "brass_key", "deadline": 5,
             "reward": 10, "requires": []},
            {"delivery_id": "lantern_supply", "destination_scene": "sanctuary",
             "required_item": "brass_key", "deadline": 8,
             "reward": 20, "requires": ["gate_supply"]},
        ],
    }
    return source, actions


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton weather-deliveries")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    start = sub.add_parser("start")
    start.add_argument("--source-json", required=True)
    advance = sub.add_parser("advance")
    advance.add_argument("--session-json", required=True)
    advance.add_argument("--action-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    for command in ("verify", "summary", "pack"):
        item = sub.add_parser(command)
        item.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_deliveries()
            result = resume_deliveries(new_deliveries(source), actions)
        elif args.command == "start":
            result = new_deliveries(_json(args.source_json, "delivery source"))
        elif args.command == "unpack":
            result = verify_delivery_package(_json(args.package_json, "delivery package"))
        else:
            saved = _json(args.session_json, "delivery session")
            if args.command == "advance":
                result = advance_deliveries(saved, _json(args.action_json, "delivery action"))
            elif args.command == "resume":
                result = resume_deliveries(saved, _json(args.actions_json, "delivery actions"))
            elif args.command == "verify":
                result = verify_deliveries(saved)
            elif args.command == "summary":
                result = delivery_summary(saved)
            else:
                result = package_deliveries(saved)
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
