"""Deterministic mission/event director over canonical offline scene travel.

Scene state remains authoritative in scene_travel. This adapter derives
objective completion, authored decisions and reputation only by replaying
legal source-bound actions. No scripts, provider calls or untrusted grants.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, QuestNode, SaveableGameplayState, dig, quest_order,
)
from skeleton.game.gameplay.scene_travel import (
    SceneTravelError, _advance as advance_scene, _id, _json, _limit,
    _object, new_session, normalize_world, original_demo,
)

SCHEMA = "skeleton.scene_mission.v1"
BUNDLE = "skeleton.scene_mission_bundle.v1"
MAX_MISSIONS = 32
MAX_CHOICES = 24
MAX_ENDINGS = 8
MAX_ACTIONS = 512
MAX_BYTES = 2 * 1024 * 1024
MAX_SOURCE_BYTES = 131072


def _size(value: Any, maximum: int) -> None:
    try:
        data = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SceneTravelError("invalid mission JSON") from exc
    if len(data) > maximum:
        raise SceneTravelError("mission JSON budget exceeded")


def _ids(value: Any, label: str, maximum: int) -> list[str]:
    if type(value) is not list or len(value) > maximum:
        raise SceneTravelError(f"invalid {label} list")
    ids = [_id(x, label) for x in value]
    if len(set(ids)) != len(ids):
        raise SceneTravelError(f"duplicate {label}")
    return ids


def normalize_mission_world(raw: Any) -> dict[str, Any]:
    _size(raw, MAX_SOURCE_BYTES)
    obj = _object(raw, {
        "schema_version", "director_id", "world", "choices",
        "missions", "endings",
    }, "mission director")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported mission director schema")
    director_id = _id(obj["director_id"], "director_id")
    world = normalize_world(obj["world"])
    scenes = {s["id"]: s for s in world["scenes"]}
    pickup_keys = {
        s["id"] + ":" + p["id"]
        for s in world["scenes"] for p in s["pickups"]
    }
    raw_choices = obj["choices"]
    if type(raw_choices) is not list or len(raw_choices) > MAX_CHOICES:
        raise SceneTravelError("invalid director choice count")
    choices = []
    for raw_choice in raw_choices:
        choice = _object(raw_choice, {"id", "scene_id", "options"}, "choice")
        scene_id = _id(choice["scene_id"], "choice scene")
        if scene_id not in scenes or scenes[scene_id]["ending"] is not None:
            raise SceneTravelError("choice must belong to a playable scene")
        options = choice["options"]
        if type(options) is not list or not 2 <= len(options) <= 8:
            raise SceneTravelError("choice needs 2..8 options")
        clean = []
        for raw_option in options:
            option = _object(raw_option, {"id", "reputation"}, "choice option")
            clean.append({
                "id": _id(option["id"], "option_id"),
                "reputation": _limit(option["reputation"], "reputation", -100, 100),
            })
        if len({o["id"] for o in clean}) != len(clean):
            raise SceneTravelError("duplicate option id")
        choices.append({
            "id": _id(choice["id"], "choice_id"), "scene_id": scene_id,
            "options": sorted(clean, key=lambda o: o["id"]),
        })
    choices.sort(key=lambda c: c["id"])
    if len({c["id"] for c in choices}) != len(choices):
        raise SceneTravelError("duplicate director choice")
    choice_targets = {
        c["id"] + ":" + o["id"] for c in choices for o in c["options"]
    }
    raw_missions = obj["missions"]
    if type(raw_missions) is not list or not 1 <= len(raw_missions) <= MAX_MISSIONS:
        raise SceneTravelError("invalid mission count")
    missions = []
    for raw_mission in raw_missions:
        mission = _object(
            raw_mission, {"id", "requires", "trigger", "reputation"},
            "mission",
        )
        trigger = _object(mission["trigger"], {"kind", "value"}, "mission trigger")
        kind = trigger["kind"]
        value = _id(trigger["value"], "trigger value")
        if kind == "visit":
            valid = value in scenes
        elif kind == "collect":
            valid = value in pickup_keys
        elif kind == "choice":
            valid = value in choice_targets
        else:
            raise SceneTravelError("unsupported mission trigger")
        if not valid:
            raise SceneTravelError("mission trigger references missing authored content")
        missions.append({
            "id": _id(mission["id"], "mission_id"),
            "requires": sorted(_ids(mission["requires"], "mission dependency",
                                     MAX_MISSIONS)),
            "trigger": {"kind": kind, "value": value},
            "reputation": _limit(mission["reputation"], "mission reputation", 0, 1000),
        })
    missions.sort(key=lambda m: m["id"])
    if len({m["id"] for m in missions}) != len(missions):
        raise SceneTravelError("duplicate mission id")
    try:
        order = quest_order([
            QuestNode(m["id"], tuple(m["requires"]), dig(m["trigger"]))
            for m in missions
        ])
    except ValueError as exc:
        raise SceneTravelError("mission dependency graph invalid") from exc
    by_id = {m["id"]: m for m in missions}
    ordered = [by_id[mid] for mid in order]
    raw_endings = obj["endings"]
    if type(raw_endings) is not list or not 1 <= len(raw_endings) <= MAX_ENDINGS:
        raise SceneTravelError("invalid director ending count")
    endings = []
    for raw_ending in raw_endings:
        ending = _object(raw_ending, {
            "id", "scene_phase", "requires", "min_reputation",
        }, "director ending")
        if ending["scene_phase"] not in ("won", "lost", "draw"):
            raise SceneTravelError("invalid director ending phase")
        required = _ids(ending["requires"], "ending mission", MAX_MISSIONS)
        if not set(required) <= set(by_id):
            raise SceneTravelError("ending references missing mission")
        endings.append({
            "id": _id(ending["id"], "ending_id"),
            "scene_phase": ending["scene_phase"], "requires": sorted(required),
            "min_reputation": _limit(
                ending["min_reputation"], "ending reputation", -10000, 10000,
            ),
        })
    endings.sort(key=lambda e: e["id"])
    if len({e["id"] for e in endings}) != len(endings):
        raise SceneTravelError("duplicate director ending")
    return {
        "schema_version": SCHEMA, "director_id": director_id,
        "world": world, "choices": choices, "missions": ordered,
        "endings": endings,
    }


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["world"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state), canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_mission(source: Any) -> dict[str, Any]:
    spec = normalize_mission_world(source)
    state = {
        "tick": 0, "scene": new_session(spec["world"]),
        "choices": {}, "missions": [], "reputation": 0,
        "phase": "active", "ending": None,
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest, "save": _save(spec, state),
    }


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid director action")
    kind = raw.get("kind")
    if kind == "scene":
        _object(raw, {"kind", "action"}, "director scene action")
        nested = raw["action"]
        if type(nested) is not dict:
            raise SceneTravelError("invalid nested scene action")
        return {"kind": kind, "action": nested}
    if kind == "choose":
        _object(raw, {"kind", "choice_id", "option_id"}, "director choice action")
        return {
            "kind": kind, "choice_id": _id(raw["choice_id"], "choice_id"),
            "option_id": _id(raw["option_id"], "option_id"),
        }
    if kind == "finish":
        _object(raw, {"kind", "ending_id"}, "director ending action")
        return {"kind": kind, "ending_id": _id(raw["ending_id"], "ending_id")}
    raise SceneTravelError("unsupported director action")


def _event_bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "mission.action", e["action"]["kind"], e["receipt"])
        for i, e in enumerate(journal)
    )).digest


def _satisfied(mission: dict[str, Any], state: dict[str, Any]) -> bool:
    trigger = mission["trigger"]
    kind, value = trigger["kind"], trigger["value"]
    scene = state["scene"]["state"]
    if kind == "visit":
        return value in scene["visited"]
    if kind == "collect":
        return value in scene["collected"]
    return any(
        choice_id + ":" + option_id == value
        for choice_id, option_id in state["choices"].items()
    )


def _advance(session: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = session["source"], session["state"]
    if old["phase"] != "active":
        raise SceneTravelError("director already terminal")
    if old["tick"] >= MAX_ACTIONS:
        raise SceneTravelError("director action budget exhausted")
    action = _action(raw)
    state = {
        **old, "tick": old["tick"] + 1,
        "choices": dict(old["choices"]), "missions": list(old["missions"]),
    }
    if action["kind"] == "scene":
        if old["scene"]["state"]["phase"] != "active":
            raise SceneTravelError("scene already terminal")
        state["scene"] = advance_scene(old["scene"], action["action"])
    elif action["kind"] == "choose":
        choice = next(
            (c for c in source["choices"] if c["id"] == action["choice_id"]), None
        )
        if choice is None or choice["scene_id"] != old["scene"]["state"]["scene_id"]:
            raise SceneTravelError("choice unavailable at current scene")
        if old["scene"]["state"]["phase"] != "active":
            raise SceneTravelError("choice unavailable after terminal scene")
        if choice["id"] in state["choices"]:
            raise SceneTravelError("choice already resolved")
        option = next(
            (o for o in choice["options"] if o["id"] == action["option_id"]), None
        )
        if option is None:
            raise SceneTravelError("invalid choice option")
        state["choices"][choice["id"]] = option["id"]
        state["reputation"] += option["reputation"]
    else:
        ending = next(
            (e for e in source["endings"] if e["id"] == action["ending_id"]), None
        )
        if ending is None or ending["scene_phase"] != old["scene"]["state"]["phase"]:
            raise SceneTravelError("director ending outcome not earned")
        if not set(ending["requires"]) <= set(state["missions"]):
            raise SceneTravelError("director ending mission requirements unmet")
        if state["reputation"] < ending["min_reputation"]:
            raise SceneTravelError("director ending reputation requirement unmet")
        state["phase"] = "finished"
        state["ending"] = ending["id"]
    if action["kind"] != "finish":
        # Source-ordered DAG ensures dependent missions cannot be granted early.
        for mission in source["missions"]:
            if mission["id"] in state["missions"]:
                continue
            if set(mission["requires"]) <= set(state["missions"]) and _satisfied(
                mission, state,
            ):
                state["missions"].append(mission["id"])
                state["reputation"] += mission["reputation"]
    if not -10000 <= state["reputation"] <= 10000:
        raise SceneTravelError("director reputation budget exceeded")
    event = {
        "sequence": old["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": session["source_digest"],
        "state": state, "state_digest": dig(state),
        "journal": journal, "event_bus_digest": _event_bus(journal),
        "save": _save(source, state, session["save"]),
    }
    _size(result, MAX_BYTES)
    return result


def verify_mission(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "director session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported director save schema")
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise SceneTravelError("invalid director journal")
    rebuilt = new_mission(obj["source"])
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid director journal event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("director replay event mismatch")
    if rebuilt != obj:
        raise SceneTravelError("director source or save mismatch")
    return rebuilt


def resume_mission(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_mission(payload)
    if type(actions) is not list or len(actions) + len(session["journal"]) > MAX_ACTIONS:
        raise SceneTravelError("invalid director action batch")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_mission(source: Any, actions: Any) -> dict[str, Any]:
    return resume_mission(new_mission(source), actions)


def export_mission(payload: Any) -> dict[str, Any]:
    session = verify_mission(payload)
    bundle = {
        "schema_version": BUNDLE, "source_digest": session["source_digest"],
        "state_digest": session["state_digest"], "session": session,
    }
    bundle["checksum"] = dig(bundle)
    _size(bundle, MAX_BYTES)
    return bundle


def import_mission(payload: Any) -> dict[str, Any]:
    _size(payload, MAX_BYTES)
    obj = _object(payload, {
        "schema_version", "source_digest", "state_digest", "session", "checksum",
    }, "director bundle")
    if obj["schema_version"] != BUNDLE:
        raise SceneTravelError("unsupported director bundle schema")
    if obj["checksum"] != dig({k: v for k, v in obj.items() if k != "checksum"}):
        raise SceneTravelError("director bundle checksum mismatch")
    session = verify_mission(obj["session"])
    if (session["source_digest"] != obj["source_digest"]
            or session["state_digest"] != obj["state_digest"]):
        raise SceneTravelError("director bundle source/state mismatch")
    return session


def original_mission() -> dict[str, Any]:
    world, _ = original_demo()
    return {
        "schema_version": SCHEMA, "director_id": "harbor_lantern",
        "world": world,
        "choices": [{
            "id": "restore_lantern", "scene_id": "quay",
            "options": [
                {"id": "help", "reputation": 2},
                {"id": "decline", "reputation": -2},
            ],
        }],
        "missions": [
            {"id": "pledge", "requires": [],
             "trigger": {"kind": "choice", "value": "restore_lantern:help"},
             "reputation": 1},
            {"id": "recover_key", "requires": ["pledge"],
             "trigger": {"kind": "collect", "value": "quay:find_key"},
             "reputation": 1},
            {"id": "reach_sanctuary", "requires": ["recover_key"],
             "trigger": {"kind": "visit", "value": "sanctuary"},
             "reputation": 2},
        ],
        "endings": [
            {"id": "lantern_restored", "scene_phase": "won",
             "requires": ["reach_sanctuary"], "min_reputation": 5},
            {"id": "unpledged_victory", "scene_phase": "won",
             "requires": [], "min_reputation": -10000},
            {"id": "sinkhole_failure", "scene_phase": "lost",
             "requires": [], "min_reputation": -10000},
            {"id": "time_exhausted", "scene_phase": "draw",
             "requires": [], "min_reputation": -10000},
        ],
    }


def demo_actions() -> list[dict[str, Any]]:
    return [
        {"kind": "choose", "choice_id": "restore_lantern", "option_id": "help"},
        {"kind": "scene", "action": {"kind": "collect", "pickup_id": "find_key"}},
        {"kind": "scene", "action": {"kind": "travel", "exit_id": "north"}},
        {"kind": "scene", "action": {"kind": "travel", "exit_id": "inside"}},
        {"kind": "finish", "ending_id": "lantern_restored"},
    ]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-mission")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play the original source-bound mission")
    sim = sub.add_parser("simulate")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    export = sub.add_parser("export")
    export.add_argument("--session-json", required=True)
    imported = sub.add_parser("import")
    imported.add_argument("--bundle-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = simulate_mission(original_mission(), demo_actions())
        elif args.command == "simulate":
            result = simulate_mission(
                _json(args.source_json, "mission source"),
                _json(args.actions_json, "mission actions"),
            )
        elif args.command == "resume":
            result = resume_mission(
                _json(args.session_json, "mission session", max_bytes=MAX_BYTES),
                _json(args.actions_json, "mission actions"),
            )
        elif args.command == "verify":
            result = verify_mission(
                _json(args.session_json, "mission session", max_bytes=MAX_BYTES)
            )
        elif args.command == "export":
            result = export_mission(
                _json(args.session_json, "mission session", max_bytes=MAX_BYTES)
            )
        else:
            result = import_mission(
                _json(args.bundle_json, "mission bundle", max_bytes=MAX_BYTES)
            )
        _size(result, MAX_BYTES)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
