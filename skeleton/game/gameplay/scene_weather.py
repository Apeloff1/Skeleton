"""Replay-verifiable weather gates over canonical offline scene traversal.

Weather is authored data, never executable content. Every legal scene action
is applied by the canonical scene engine; the overlay only gates exits and
accounts for bounded wait ticks. Digests are not signatures.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, dig,
)
from skeleton.game.gameplay.scene_travel import (
    MAX_JSON_BYTES, SceneTravelError, _advance as advance_scene,
    _id, _json, _limit, _object, new_session as new_scene,
    normalize_world, original_demo,
)

SCHEMA = "skeleton.scene_weather.v1"
CONDITIONS = ("clear", "rain", "storm", "fog")
MAX_RULES = 128
MAX_CYCLE = 16


def normalize_weather(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "world", "cycle", "blocked_exits"},
                  "weather source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather source schema")
    world = normalize_world(obj["world"])
    cycle = obj["cycle"]
    if type(cycle) is not list or not 1 <= len(cycle) <= MAX_CYCLE:
        raise SceneTravelError("invalid weather cycle length")
    if any(type(condition) is not str or condition not in CONDITIONS
           for condition in cycle):
        raise SceneTravelError("unsupported weather condition")
    raw_rules = obj["blocked_exits"]
    if type(raw_rules) is not list or len(raw_rules) > MAX_RULES:
        raise SceneTravelError("weather gate count exceeded")
    exits = {
        (scene["id"], exit_data["id"])
        for scene in world["scenes"] for exit_data in scene["exits"]
    }
    rules = []
    seen = set()
    for raw_rule in raw_rules:
        rule = _object(raw_rule, {"scene_id", "exit_id", "conditions"},
                       "weather gate")
        scene_id = _id(rule["scene_id"], "weather scene_id")
        exit_id = _id(rule["exit_id"], "weather exit_id")
        key = (scene_id, exit_id)
        if key not in exits or key in seen:
            raise SceneTravelError("unknown or duplicate weather exit gate")
        seen.add(key)
        conditions = rule["conditions"]
        if (type(conditions) is not list or not 1 <= len(conditions) <= len(CONDITIONS)
                or any(type(value) is not str or value not in CONDITIONS
                       for value in conditions)
                or len(set(conditions)) != len(conditions)):
            raise SceneTravelError("invalid weather gate conditions")
        if not set(conditions) <= set(cycle):
            raise SceneTravelError("weather gate condition absent from cycle")
        rules.append({
            "scene_id": scene_id, "exit_id": exit_id,
            "conditions": sorted(conditions),
        })
    rules.sort(key=lambda rule: (rule["scene_id"], rule["exit_id"]))
    return {
        "schema_version": SCHEMA, "world": world,
        "cycle": list(cycle), "blocked_exits": rules,
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _event_bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "weather.action", event["action"]["kind"],
                      event["receipt"])
        for i, event in enumerate(journal)
    )).digest


def new_session(source: Any) -> dict[str, Any]:
    spec = normalize_weather(source)
    state = {
        "tick": 0, "scene": new_scene(spec["world"]),
        "weather": spec["cycle"][0], "phase": "active",
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest,
        "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid weather action")
    kind = raw.get("kind")
    if kind == "wait":
        _object(raw, {"kind"}, "wait action")
        return {"kind": "wait"}
    if kind == "scene":
        _object(raw, {"kind", "action"}, "weather scene action")
        nested = raw["action"]
        if type(nested) is not dict:
            raise SceneTravelError("invalid nested weather scene action")
        if nested.get("kind") == "travel":
            _object(nested, {"kind", "exit_id"}, "weather travel")
            _id(nested["exit_id"], "exit_id")
        elif nested.get("kind") == "collect":
            _object(nested, {"kind", "pickup_id"}, "weather pickup")
            _id(nested["pickup_id"], "pickup_id")
        else:
            raise SceneTravelError("unsupported nested weather action")
        return {"kind": kind, "action": dict(nested)}
    raise SceneTravelError("unsupported weather action kind")


def _advance(session: dict[str, Any], raw_action: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active":
        raise SceneTravelError("weather journey already terminal")
    action = _action(raw_action)
    scene = old["scene"]
    if action["kind"] == "scene":
        nested = action["action"]
        if nested["kind"] == "travel":
            for rule in source["blocked_exits"]:
                if (rule["scene_id"] == scene["state"]["scene_id"]
                        and rule["exit_id"] == nested["exit_id"]
                        and old["weather"] in rule["conditions"]):
                    raise SceneTravelError("exit blocked by current weather")
        scene = advance_scene(scene, nested)
    tick = old["tick"] + 1
    phase = scene["state"]["phase"]
    if phase == "active" and tick >= source["world"]["step_limit"]:
        phase = "draw"
    state = {
        "tick": tick, "scene": scene,
        "weather": source["cycle"][tick % len(source["cycle"])],
        "phase": phase,
    }
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    return {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "event_bus_digest": _event_bus(journal),
        "save": _save(source, state, session["save"]),
    }


def verify_session(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "weather session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported weather save schema")
    rebuilt = new_session(obj["source"])
    journal = obj["journal"]
    if (type(journal) is not list
            or len(journal) > rebuilt["source"]["world"]["step_limit"]):
        raise SceneTravelError("invalid weather journal budget")
    for event in journal:
        if type(event) is not dict:
            raise SceneTravelError("invalid weather journal entry")
        try:
            rebuilt = _advance(rebuilt, event["action"])
        except (KeyError, TypeError) as exc:
            raise SceneTravelError("malformed weather journal") from exc
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("weather journal receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("weather save or source lineage mismatch")
    return rebuilt


def resume_session(raw: Any, actions: Any) -> dict[str, Any]:
    session = verify_session(raw)
    if type(actions) is not list or (
        len(session["journal"]) + len(actions)
        > session["source"]["world"]["step_limit"]
    ):
        raise SceneTravelError("weather action batch exceeds step budget")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate(source: Any, actions: Any) -> dict[str, Any]:
    return resume_session(new_session(source), actions)


def original_weather_demo() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    world, actions = original_demo()
    source = {
        "schema_version": SCHEMA, "world": world,
        "cycle": ["storm", "clear", "clear"],
        "blocked_exits": [
            {"scene_id": "quay", "exit_id": "north", "conditions": ["storm"]},
        ],
    }
    return source, [{"kind": "scene", "action": action} for action in actions]


def _export(result: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise SceneTravelError("invalid weather export") from exc
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise SceneTravelError("weather export exceeds 128 KiB")
    return encoded


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    play = sub.add_parser("simulate")
    play.add_argument("--source-json", required=True)
    play.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_weather_demo()
            result = simulate(source, actions)
        elif args.command == "simulate":
            result = simulate(_json(args.source_json, "weather source"),
                              _json(args.actions_json, "weather actions"))
        elif args.command == "verify":
            result = verify_session(_json(args.session_json, "weather save"))
        else:
            result = resume_session(
                _json(args.session_json, "weather save"),
                _json(args.actions_json, "weather actions"),
            )
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
