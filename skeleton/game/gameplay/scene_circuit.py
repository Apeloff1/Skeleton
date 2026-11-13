"""Replay-verified switch puzzles and conditional scene exits.

Canonical scene travel still owns movement, inventory, endings and its own
checkpoint. Circuit state is derived only from legal source-bound actions.
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
    SceneTravelError, _advance as advance_scene, _id, _object, _json,
    new_session, normalize_world, original_demo,
)

SCHEMA = "skeleton.scene_circuit.v1"
BUNDLE = "skeleton.scene_circuit_bundle.v1"
MAX_ACTIONS = 96
MAX_BYTES = 2 * 1024 * 1024


def _ids(raw: Any, label: str) -> list[str]:
    if type(raw) is not list or len(raw) > 16:
        raise SceneTravelError(f"invalid {label} list")
    values = [_id(x, label) for x in raw]
    if len(set(values)) != len(values):
        raise SceneTravelError(f"duplicate {label}")
    return sorted(values)


def normalize_circuit(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {"schema_version", "circuit_id", "world",
                        "switches", "gates"}, "circuit source")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported circuit schema")
    circuit_id = _id(obj["circuit_id"], "circuit id")
    world = normalize_world(obj["world"])
    playable = {s["id"]: s for s in world["scenes"] if s["ending"] is None}
    switches = obj["switches"]
    if type(switches) is not list or not 1 <= len(switches) <= 16:
        raise SceneTravelError("invalid circuit switch count")
    clean_switches, names = [], set()
    for raw_switch in switches:
        switch = _object(raw_switch, {"id", "scene_id", "initial_on"}, "switch")
        key = _id(switch["id"], "switch id")
        scene = _id(switch["scene_id"], "switch scene")
        if key in names or scene not in playable or type(switch["initial_on"]) is not bool:
            raise SceneTravelError("invalid or duplicate circuit switch")
        names.add(key)
        clean_switches.append({"id": key, "scene_id": scene,
                               "initial_on": switch["initial_on"]})
    gates = obj["gates"]
    if type(gates) is not list or not 1 <= len(gates) <= 32:
        raise SceneTravelError("invalid circuit gate count")
    clean_gates, edges = [], set()
    for raw_gate in gates:
        gate = _object(raw_gate, {"scene_id", "exit_id",
                                  "requires_on", "requires_off"}, "gate")
        scene = _id(gate["scene_id"], "gate scene")
        exit_id = _id(gate["exit_id"], "gate exit")
        if scene not in playable or exit_id not in {
            x["id"] for x in playable[scene]["exits"]
        } or (scene, exit_id) in edges:
            raise SceneTravelError("circuit gate references invalid exit")
        edges.add((scene, exit_id))
        on = _ids(gate["requires_on"], "required on")
        off = _ids(gate["requires_off"], "required off")
        if not (on or off) or set(on) & set(off) or not set(on + off) <= names:
            raise SceneTravelError("invalid circuit gate switch condition")
        clean_gates.append({"scene_id": scene, "exit_id": exit_id,
                            "requires_on": on, "requires_off": off})
    return {"schema_version": SCHEMA, "circuit_id": circuit_id,
            "world": world,
            "switches": sorted(clean_switches, key=lambda x: x["id"]),
            "gates": sorted(clean_gates, key=lambda x: (x["scene_id"], x["exit_id"]))}


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state), canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _events(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(i, "scene.circuit", x["action"]["kind"], x["receipt"])
        for i, x in enumerate(journal)
    )).digest


def new_circuit(source: Any) -> dict[str, Any]:
    spec = normalize_circuit(source)
    state = {"tick": 0,
             "switches": {s["id"]: s["initial_on"] for s in spec["switches"]},
             "scene": new_session(spec["world"])}
    return {"schema_version": SCHEMA, "source": spec,
            "source_digest": dig(spec), "state": state,
            "state_digest": dig(state), "journal": [],
            "event_bus_digest": EventBus().digest, "save": _save(spec, state)}


def _action(raw: Any) -> dict[str, str]:
    if type(raw) is not dict:
        raise SceneTravelError("invalid circuit action")
    kind = raw.get("kind")
    fields = {"toggle": ("switch_id",), "collect": ("pickup_id",),
              "travel": ("exit_id",)}
    if kind not in fields:
        raise SceneTravelError("unsupported circuit action")
    key = fields[kind][0]
    _object(raw, {"kind", key}, "circuit action")
    return {"kind": kind, key: _id(raw[key], key)}


def _advance(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = snapshot["source"], snapshot["state"]
    if old["scene"]["state"]["phase"] != "active" or old["tick"] >= MAX_ACTIONS:
        raise SceneTravelError("circuit terminal or action budget exceeded")
    action = _action(raw)
    state = {"tick": old["tick"] + 1,
             "switches": dict(old["switches"]), "scene": old["scene"]}
    scene_id = old["scene"]["state"]["scene_id"]
    if action["kind"] == "toggle":
        switch = next((s for s in source["switches"]
                       if s["id"] == action["switch_id"]), None)
        if switch is None or switch["scene_id"] != scene_id:
            raise SceneTravelError("switch is not in current scene")
        key = switch["id"]
        state["switches"][key] = not state["switches"][key]
    else:
        if action["kind"] == "travel":
            gate = next((g for g in source["gates"]
                         if g["scene_id"] == scene_id
                         and g["exit_id"] == action["exit_id"]), None)
            if gate is not None and (
                any(not state["switches"][key] for key in gate["requires_on"])
                or any(state["switches"][key] for key in gate["requires_off"])
            ):
                raise SceneTravelError("circuit gate is locked")
        state["scene"] = advance_scene(old["scene"], action)
    event = {"sequence": old["tick"], "action": action,
             "before": snapshot["state_digest"], "after": dig(state)}
    event["receipt"] = dig(event)
    journal = [*snapshot["journal"], event]
    return {"schema_version": SCHEMA, "source": source,
            "source_digest": snapshot["source_digest"], "state": state,
            "state_digest": dig(state), "journal": journal,
            "event_bus_digest": _events(journal),
            "save": _save(source, state, snapshot["save"])}


def verify_circuit(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "source", "source_digest",
                            "state", "state_digest", "journal",
                            "event_bus_digest", "save"}, "circuit save")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported circuit save")
    rebuilt = new_circuit(obj["source"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > MAX_ACTIONS:
        raise SceneTravelError("invalid circuit journal")
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise SceneTravelError("invalid circuit event")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("circuit action replay mismatch")
    if rebuilt != obj:
        raise SceneTravelError("circuit save or source lineage mismatch")
    return rebuilt


def resume_circuit(payload: Any, actions: Any) -> dict[str, Any]:
    snapshot = verify_circuit(payload)
    if type(actions) is not list or len(actions) + len(snapshot["journal"]) > MAX_ACTIONS:
        raise SceneTravelError("invalid circuit action batch")
    for action in actions:
        snapshot = _advance(snapshot, action)
    return snapshot


def simulate_circuit(source: Any, actions: Any) -> dict[str, Any]:
    return resume_circuit(new_circuit(source), actions)


def export_circuit(payload: Any) -> dict[str, Any]:
    session = verify_circuit(payload)
    bundle = {"schema_version": BUNDLE, "session": session,
              "session_digest": dig(session)}
    if len(json.dumps(bundle, sort_keys=True, allow_nan=False).encode()) > MAX_BYTES:
        raise SceneTravelError("circuit bundle budget exceeded")
    return bundle


def import_circuit(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {"schema_version", "session", "session_digest"},
                  "circuit bundle")
    if obj["schema_version"] != BUNDLE or dig(obj["session"]) != obj["session_digest"]:
        raise SceneTravelError("circuit bundle identity mismatch")
    return verify_circuit(obj["session"])


def original_circuit() -> tuple[dict[str, Any], list[dict[str, str]]]:
    world, travel = original_demo()
    source = {"schema_version": SCHEMA, "circuit_id": "quay_signal",
              "world": world, "switches": [
                  {"id": "quay_lantern", "scene_id": "quay", "initial_on": False},
                  {"id": "gate_pulse", "scene_id": "gate", "initial_on": True},
              ], "gates": [
                  {"scene_id": "quay", "exit_id": "north",
                   "requires_on": ["quay_lantern"], "requires_off": []},
                  {"scene_id": "gate", "exit_id": "inside",
                   "requires_on": ["gate_pulse"], "requires_off": []},
              ]}
    return source, [{"kind": "toggle", "switch_id": "quay_lantern"}, *travel]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton scene-circuit")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    for name, options in {
        "preview": ("source-json",), "simulate": ("source-json", "actions-json"),
        "resume": ("session-json", "actions-json"),
        "verify": ("session-json",), "export": ("session-json",),
        "import": ("bundle-json",),
    }.items():
        command = sub.add_parser(name)
        for option in options:
            command.add_argument("--" + option, required=True)
    args = parser.parse_args(list(argv))
    try:
        read = lambda name: _json(getattr(args, name.replace("-", "_")), name,
                                  max_bytes=MAX_BYTES)
        if args.command == "demo":
            source, actions = original_circuit()
            result = simulate_circuit(source, actions)
        elif args.command == "preview":
            result = normalize_circuit(read("source-json"))
        elif args.command == "simulate":
            result = simulate_circuit(read("source-json"), read("actions-json"))
        elif args.command == "resume":
            result = resume_circuit(read("session-json"), read("actions-json"))
        elif args.command == "verify":
            result = verify_circuit(read("session-json"))
        elif args.command == "export":
            result = export_circuit(read("session-json"))
        else:
            result = import_circuit(read("bundle-json"))
        output = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(output.encode()) > MAX_BYTES:
            raise SceneTravelError("circuit output budget exceeded")
        print(output)
        return 0
    except (SceneTravelError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
