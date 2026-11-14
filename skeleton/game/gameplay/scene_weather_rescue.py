"""Weather-aware NPC rescue missions with canonical travel and earned rewards.

The weather/scene engines own every travel, pickup, clock tick and weather
gate. Rescues, exposure and shelter settlement are replay-derived overlays,
never accepted as client-supplied reputation or currency claims.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _id, _json, _limit, _object,
)
from skeleton.game.gameplay.scene_weather import (
    _action as weather_action, _advance as advance_weather, _export,
    new_session as new_weather, normalize_weather,
    original_weather_demo,
)

SCHEMA = "skeleton.weather_rescue.v1"
PACKAGE_SCHEMA = "skeleton.weather_rescue_package.v1"
MAX_NPCS = 8
MAX_TOTAL_REWARD = 100000


def normalize_rescue(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "weather", "npcs"}, "rescue source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported rescue source schema")
    weather = normalize_weather(obj["weather"])
    scenes = {scene["id"]: scene for scene in weather["world"]["scenes"]}
    raw_npcs = obj["npcs"]
    if type(raw_npcs) is not list or not 1 <= len(raw_npcs) <= MAX_NPCS:
        raise SceneTravelError("invalid rescue NPC count")
    npcs = []
    seen: set[str] = set()
    total = 0
    for raw_npc in raw_npcs:
        npc = _object(raw_npc, {
            "npc_id", "origin_scene", "shelter_scene",
            "deadline", "max_storm_exposure", "reward",
        }, "rescue NPC")
        npc_id = _id(npc["npc_id"], "npc_id")
        origin = _id(npc["origin_scene"], "origin_scene")
        shelter = _id(npc["shelter_scene"], "shelter_scene")
        if npc_id in seen:
            raise SceneTravelError("duplicate rescue NPC")
        if origin not in scenes or shelter not in scenes or origin == shelter:
            raise SceneTravelError("invalid rescue origin or shelter")
        if scenes[origin]["ending"] is not None or scenes[shelter]["ending"] is not None:
            raise SceneTravelError("rescue scenes must permit active interaction")
        seen.add(npc_id)
        reward = _limit(npc["reward"], "reward", 1, 10000)
        total += reward
        if total > MAX_TOTAL_REWARD:
            raise SceneTravelError("rescue reward budget exceeded")
        npcs.append({
            "npc_id": npc_id, "origin_scene": origin,
            "shelter_scene": shelter,
            "deadline": _limit(npc["deadline"], "deadline", 1,
                               weather["world"]["step_limit"]),
            "max_storm_exposure": _limit(
                npc["max_storm_exposure"], "max_storm_exposure", 0, 8,
            ),
            "reward": reward,
        })
    npcs.sort(key=lambda npc: npc["npc_id"])
    result = {"schema_version": SCHEMA, "weather": weather, "npcs": npcs}
    _export(result)
    return result


def _save(source: dict[str, Any], weather: dict[str, Any],
          state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_version": "skeleton.weather_rescue_save.v1",
        "source_digest": dig(source),
        "weather_save_digest": dig(weather["save"]),
        "state_digest": dig(state),
        "tick": state["tick"],
        "parent_digest": None if parent is None else dig(parent),
    }


def _snapshot(source: dict[str, Any], weather: dict[str, Any],
              state: dict[str, Any], parent: dict[str, Any] | None) -> dict[str, Any]:
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "weather_session": weather,
        "state": state, "state_digest": dig(state),
        "save": _save(source, weather, state, parent),
    }
    _export(result)
    return result


def new_rescue(source: Any) -> dict[str, Any]:
    spec = normalize_rescue(source)
    weather = new_weather(spec["weather"])
    state = {
        "tick": 0, "phase": "active", "earned": 0,
        "npcs": {
            npc["npc_id"]: {"status": "waiting", "exposure": 0}
            for npc in spec["npcs"]
        },
        "journal": [],
    }
    return _snapshot(spec, weather, state, None)


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid rescue action")
    kind = raw.get("kind")
    if kind == "weather":
        _object(raw, {"kind", "action"}, "rescue weather action")
        return {"kind": kind, "action": weather_action(raw["action"])}
    if kind in ("rescue", "shelter"):
        _object(raw, {"kind", "npc_id"}, "rescue NPC action")
        return {"kind": kind, "npc_id": _id(raw["npc_id"], "npc_id")}
    raise SceneTravelError("unsupported rescue action")


def _advance(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    if snapshot["state"]["phase"] != "active":
        raise SceneTravelError("rescue journey already terminal")
    action = _action(raw)
    source, old = snapshot["source"], snapshot["state"]
    weather_before = snapshot["weather_session"]
    location = weather_before["state"]["scene"]["state"]["scene_id"]
    npcs = {npc["npc_id"]: npc for npc in source["npcs"]}
    if action["kind"] != "weather":
        npc_id = action["npc_id"]
        if npc_id not in npcs:
            raise SceneTravelError("unknown rescue NPC")
        npc = npcs[npc_id]
        status = old["npcs"][npc_id]["status"]
        expected = "waiting" if action["kind"] == "rescue" else "escorting"
        destination = npc["origin_scene"] if action["kind"] == "rescue" else npc["shelter_scene"]
        if status != expected or location != destination:
            raise SceneTravelError("rescue action unavailable at this scene or status")
    weather = advance_weather(
        weather_before, action["action"] if action["kind"] == "weather"
        else {"kind": "wait"},
    )
    tick = weather["state"]["tick"]
    current_weather = weather["state"]["weather"]
    npc_state = {key: dict(value) for key, value in old["npcs"].items()}
    if action["kind"] == "rescue":
        npc_state[action["npc_id"]]["status"] = "escorting"
    changes = []
    earned = old["earned"]
    for npc in source["npcs"]:
        npc_id = npc["npc_id"]
        entry = npc_state[npc_id]
        previous = old["npcs"][npc_id]
        if entry["status"] in ("safe", "lost"):
            continue
        if entry["status"] == "escorting" and current_weather == "storm":
            entry["exposure"] += 1
        if tick > npc["deadline"] or entry["exposure"] > npc["max_storm_exposure"]:
            entry["status"] = "lost"
        elif action["kind"] == "shelter" and action["npc_id"] == npc_id:
            entry["status"] = "safe"
            earned += npc["reward"]
        if earned > MAX_TOTAL_REWARD:
            raise SceneTravelError("rescue earned reward overflow")
        if entry != previous:
            changes.append({
                "npc_id": npc_id, "status": entry["status"],
                "exposure": entry["exposure"],
                "reward": npc["reward"] if entry["status"] == "safe" else 0,
            })
    statuses = {entry["status"] for entry in npc_state.values()}
    if statuses == {"safe"}:
        phase = "won"
    elif not statuses.intersection({"waiting", "escorting"}):
        phase = "lost"
    elif weather["state"]["phase"] != "active":
        phase = "lost"
    else:
        phase = "active"
    # Hash the post-action NPC projection, not a partially built journal
    # containing the event itself. This avoids self-referential receipts.
    projection = {
        "tick": tick, "phase": phase, "earned": earned, "npcs": npc_state,
    }
    event = {
        "sequence": old["tick"], "action": action,
        "before": snapshot["state_digest"], "after": dig(projection),
        "weather_state_digest": weather["state_digest"],
        "changes": changes, "earned_delta": earned - old["earned"],
    }
    event["receipt"] = dig(event)
    state = {**projection, "journal": [*old["journal"], event]}
    return _snapshot(source, weather, state, snapshot["save"])


def verify_rescue(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest",
        "weather_session", "state", "state_digest", "save",
    }, "rescue checkpoint")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported rescue checkpoint schema")
    _export(obj)
    rebuilt = new_rescue(obj["source"])
    journal = obj["state"]["journal"] if type(obj["state"]) is dict else None
    if type(journal) is not list or len(journal) > rebuilt["source"]["weather"]["world"]["step_limit"]:
        raise SceneTravelError("invalid rescue journal budget")
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid rescue journal")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["state"]["journal"][-1] != event:
            raise SceneTravelError("rescue event receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("rescue save, reward or source lineage mismatch")
    return rebuilt


def advance_rescue(raw: Any, action: Any) -> dict[str, Any]:
    return _advance(verify_rescue(raw), action)


def play_rescue(source: Any, actions: Any, *, resume: Any = None) -> dict[str, Any]:
    spec = normalize_rescue(source)
    session = new_rescue(spec) if resume is None else verify_rescue(resume)
    if session["source_digest"] != dig(spec):
        raise SceneTravelError("rescue resume source mismatch")
    if type(actions) is not list or (
        len(actions) + len(session["state"]["journal"])
        > spec["weather"]["world"]["step_limit"]
    ):
        raise SceneTravelError("rescue action budget exceeded")
    for action in actions:
        session = _advance(session, action)
    return session


def package_rescue(raw: Any) -> dict[str, Any]:
    session = verify_rescue(raw)
    state = session["state"]
    manifest = {
        "world_id": session["source"]["weather"]["world"]["world_id"],
        "source_digest": session["source_digest"],
        "state_digest": session["state_digest"],
        "weather_state_digest": session["weather_session"]["state_digest"],
        "save_digest": dig(session["save"]),
        "tick": state["tick"], "phase": state["phase"],
        "earned": state["earned"], "npcs": state["npcs"],
    }
    result = {
        "schema_version": PACKAGE_SCHEMA, "snapshot": session,
        "manifest": manifest, "claim": "integrity_checked_offline_save",
    }
    result["receipt"] = dig(result)
    _export(result)
    return result


def verify_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "snapshot", "manifest", "claim", "receipt",
    }, "rescue package")
    if obj["schema_version"] != PACKAGE_SCHEMA or obj["claim"] != "integrity_checked_offline_save":
        raise SceneTravelError("unsupported rescue package")
    _export(obj)
    expected = package_rescue(obj["snapshot"])
    if expected != obj:
        raise SceneTravelError("rescue package mismatch")
    return expected


def original_rescue() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    weather, _ = original_weather_demo()
    source = {
        "schema_version": SCHEMA, "weather": weather,
        "npcs": [{
            "npc_id": "canal_medic", "origin_scene": "quay",
            "shelter_scene": "gate", "deadline": 6,
            "max_storm_exposure": 1, "reward": 25,
        }],
    }
    actions = [
        {"kind": "rescue", "npc_id": "canal_medic"},
        {"kind": "weather", "action": {
            "kind": "scene", "action": {"kind": "collect", "pickup_id": "find_key"},
        }},
        {"kind": "weather", "action": {
            "kind": "scene", "action": {"kind": "travel", "exit_id": "north"},
        }},
        {"kind": "shelter", "npc_id": "canal_medic"},
    ]
    return source, actions


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-weather-rescue")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Rescue original NPC through storm-gated scene travel")
    start = sub.add_parser("new")
    start.add_argument("--source-json", required=True)
    play = sub.add_parser("play")
    play.add_argument("--source-json", required=True)
    play.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    pack = sub.add_parser("pack")
    pack.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            source, actions = original_rescue()
            result = play_rescue(source, actions)
        elif args.command == "new":
            result = new_rescue(_json(args.source_json, "rescue source"))
        elif args.command == "play":
            result = play_rescue(
                _json(args.source_json, "rescue source"),
                _json(args.actions_json, "rescue actions"),
            )
        elif args.command == "resume":
            saved = _json(args.session_json, "rescue checkpoint")
            result = play_rescue(
                saved["source"], _json(args.actions_json, "rescue actions"),
                resume=saved,
            )
        elif args.command == "verify":
            result = verify_rescue(_json(args.session_json, "rescue checkpoint"))
        elif args.command == "pack":
            result = package_rescue(_json(args.session_json, "rescue checkpoint"))
        else:
            result = verify_package(_json(args.package_json, "rescue package"))
        print(_export(result))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
