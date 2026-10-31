"""Source-bound offline scene traversal with deterministic endings and replay.

Canonical FLGB StateMachine, EventBus and SaveableGameplayState own the
transition, event and save contracts. Authored JSON is data only: no scripts,
filesystem paths, network access, provider calls or native rendering.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import (
    EventBus, GameplayEvent, SaveableGameplayState, StateMachine,
    StateTransition, dig,
)

SCHEMA = "skeleton.scene_travel.v1"
MAX_SCENES = 128
MAX_EXITS = 16
MAX_PICKUPS = 16
MAX_STEPS = 512
MAX_JSON_BYTES = 131072
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,63}\Z")


class SceneTravelError(ValueError):
    """Invalid authored scene, action, source identity or replay receipt."""


def _id(value: Any, label: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise SceneTravelError(f"invalid {label}")
    return value


def _object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise SceneTravelError(f"invalid {label} fields")
    return value


def _limit(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise SceneTravelError(f"invalid {label}")
    return value


def normalize_world(raw: Any) -> dict[str, Any]:
    """Validate complete authored topology and stable source identity."""
    obj = _object(
        raw, {"schema_version", "world_id", "start_scene", "step_limit", "scenes"},
        "world",
    )
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported scene travel schema")
    world_id = _id(obj["world_id"], "world_id")
    start = _id(obj["start_scene"], "start_scene")
    budget = _limit(obj["step_limit"], "step_limit", 1, MAX_STEPS)
    scenes = obj["scenes"]
    if type(scenes) is not list or not 2 <= len(scenes) <= MAX_SCENES:
        raise SceneTravelError("scene count outside 2..128")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    item_ids: set[str] = set()
    for raw_scene in scenes:
        scene = _object(raw_scene, {"id", "ending", "pickups", "exits"}, "scene")
        scene_id = _id(scene["id"], "scene_id")
        if scene_id in seen:
            raise SceneTravelError("duplicate scene_id")
        seen.add(scene_id)
        ending = scene["ending"]
        if ending not in (None, "victory", "failure") or type(ending) not in (
            str, type(None),
        ):
            raise SceneTravelError("invalid ending")
        exits = scene["exits"]
        pickups = scene["pickups"]
        if (
            type(exits) is not list or len(exits) > MAX_EXITS
            or type(pickups) is not list or len(pickups) > MAX_PICKUPS
        ):
            raise SceneTravelError("scene exit or pickup budget exceeded")
        if ending is not None and (exits or pickups):
            raise SceneTravelError("terminal scene cannot contain interactions")
        normalized_exits: list[dict[str, Any]] = []
        exit_names: set[str] = set()
        for raw_exit in exits:
            exit_data = _object(
                raw_exit, {"id", "to", "requires_item"}, "exit"
            )
            exit_id = _id(exit_data["id"], "exit_id")
            target = _id(exit_data["to"], "destination")
            required = exit_data["requires_item"]
            if required is not None:
                required = _id(required, "required_item")
            if exit_id in exit_names:
                raise SceneTravelError("duplicate exit in scene")
            exit_names.add(exit_id)
            normalized_exits.append({
                "id": exit_id, "to": target, "requires_item": required,
            })
        normalized_pickups: list[dict[str, str]] = []
        pickup_names: set[str] = set()
        for raw_pickup in pickups:
            pickup = _object(raw_pickup, {"id", "item_id"}, "pickup")
            pickup_id = _id(pickup["id"], "pickup_id")
            item_id = _id(pickup["item_id"], "item_id")
            if pickup_id in pickup_names:
                raise SceneTravelError("duplicate pickup in scene")
            pickup_names.add(pickup_id)
            item_ids.add(item_id)
            normalized_pickups.append({"id": pickup_id, "item_id": item_id})
        result.append({
            "id": scene_id, "ending": ending,
            "exits": sorted(normalized_exits, key=lambda e: e["id"]),
            "pickups": sorted(normalized_pickups, key=lambda p: p["id"]),
        })
    if start not in seen:
        raise SceneTravelError("start scene is missing")
    by_id = {scene["id"]: scene for scene in result}
    if by_id[start]["ending"] is not None:
        raise SceneTravelError("start scene cannot be terminal")
    for scene in result:
        for exit_data in scene["exits"]:
            if exit_data["to"] not in seen:
                raise SceneTravelError("exit destination missing")
            required = exit_data["requires_item"]
            if required is not None and required not in item_ids:
                raise SceneTravelError("required item is never authored")
    result.sort(key=lambda scene: scene["id"])
    return {
        "schema_version": SCHEMA, "world_id": world_id,
        "start_scene": start, "step_limit": budget, "scenes": result,
    }


def _save(spec: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=spec["world_id"], schema_version=1, tick=state["tick"],
        state_digest=dig(state), canon_digest=dig(spec),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _event_bus(journal: list[dict[str, Any]]) -> str:
    return EventBus(tuple(
        GameplayEvent(
            i, "scene.action", event["action"]["kind"], event["receipt"],
        )
        for i, event in enumerate(journal)
    )).digest


def new_session(world: Any) -> dict[str, Any]:
    spec = normalize_world(world)
    state = {
        "tick": 0, "scene_id": spec["start_scene"],
        "inventory": [], "collected": [], "visited": [spec["start_scene"]],
        "phase": "active", "ending": None,
    }
    return {
        "schema_version": SCHEMA, "world": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest,
        "save": _save(spec, state),
    }


def _scene(spec: dict[str, Any], scene_id: str) -> dict[str, Any]:
    return next(scene for scene in spec["scenes"] if scene["id"] == scene_id)


def _machine(spec: dict[str, Any]) -> StateMachine:
    return StateMachine(
        spec["start_scene"],
        [
            StateTransition(scene["id"], edge["id"], edge["to"])
            for scene in spec["scenes"] for edge in scene["exits"]
        ],
    )


def _action(raw: Any) -> dict[str, str]:
    if type(raw) is not dict or raw.get("kind") not in ("collect", "travel"):
        raise SceneTravelError("unsupported scene action")
    if raw["kind"] == "collect":
        _object(raw, {"kind", "pickup_id"}, "collect action")
        return {"kind": "collect", "pickup_id": _id(raw["pickup_id"], "pickup_id")}
    _object(raw, {"kind", "exit_id"}, "travel action")
    return {"kind": "travel", "exit_id": _id(raw["exit_id"], "exit_id")}


def _advance(session: dict[str, Any], raw_action: Any) -> dict[str, Any]:
    """Apply one action atomically; prior snapshots remain untouched."""
    spec = session["world"]
    before = session["state"]
    if before["phase"] != "active":
        raise SceneTravelError("scene travel already terminal")
    action = _action(raw_action)
    current = _scene(spec, before["scene_id"])
    state = {
        "tick": before["tick"] + 1, "scene_id": before["scene_id"],
        "inventory": list(before["inventory"]),
        "collected": list(before["collected"]),
        "visited": list(before["visited"]),
        "phase": "active", "ending": None,
    }
    if action["kind"] == "collect":
        pickup = next(
            (item for item in current["pickups"]
             if item["id"] == action["pickup_id"]), None
        )
        if pickup is None:
            raise SceneTravelError("pickup is absent from current scene")
        key = current["id"] + ":" + pickup["id"]
        if key in state["collected"]:
            raise SceneTravelError("pickup was already collected")
        state["collected"].append(key)
        state["collected"].sort()
        if pickup["item_id"] not in state["inventory"]:
            state["inventory"].append(pickup["item_id"])
            state["inventory"].sort()
    else:
        exit_data = next(
            (edge for edge in current["exits"]
             if edge["id"] == action["exit_id"]), None
        )
        if exit_data is None:
            raise SceneTravelError("exit is absent from current scene")
        required = exit_data["requires_item"]
        if required is not None and required not in state["inventory"]:
            raise SceneTravelError("exit requires an uncollected item")
        state["scene_id"] = _machine(spec).step(current["id"], exit_data["id"])
        if state["scene_id"] not in state["visited"]:
            state["visited"].append(state["scene_id"])
        ending = _scene(spec, state["scene_id"])["ending"]
        if ending is not None:
            state["phase"] = "won" if ending == "victory" else "lost"
            state["ending"] = ending
    if state["phase"] == "active" and state["tick"] >= spec["step_limit"]:
        state["phase"] = "draw"
    event = {
        "sequence": before["tick"], "action": action,
        "before": session["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*session["journal"], event]
    return {
        "schema_version": SCHEMA, "world": spec,
        "source_digest": session["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "event_bus_digest": _event_bus(journal),
        "save": _save(spec, state, session["save"]),
    }


def verify_session(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {
        "schema_version", "world", "source_digest", "state", "state_digest",
        "journal", "event_bus_digest", "save",
    }, "session")
    if obj["schema_version"] != SCHEMA:
        raise SceneTravelError("unsupported save schema")
    rebuilt = new_session(obj["world"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > rebuilt["world"]["step_limit"]:
        raise SceneTravelError("invalid journal budget")
    for event in journal:
        if type(event) is not dict:
            raise SceneTravelError("invalid journal entry")
        try:
            rebuilt = _advance(rebuilt, event["action"])
        except (KeyError, TypeError) as exc:
            raise SceneTravelError("malformed replay action") from exc
        if rebuilt["journal"][-1] != event:
            raise SceneTravelError("replay receipt mismatch")
    if rebuilt != obj:
        raise SceneTravelError("save state or source lineage mismatch")
    return rebuilt


def resume_session(payload: Any, actions: Any) -> dict[str, Any]:
    snapshot = verify_session(payload)
    if type(actions) is not list or len(actions) > MAX_STEPS:
        raise SceneTravelError("invalid action batch")
    if len(snapshot["journal"]) + len(actions) > snapshot["world"]["step_limit"]:
        raise SceneTravelError("action batch exceeds step limit")
    for action in actions:
        snapshot = _advance(snapshot, action)
    return snapshot


def simulate(world: Any, actions: Any) -> dict[str, Any]:
    return resume_session(new_session(world), actions)


def original_demo() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """An original three-scene exploration and alternate failure ending."""
    world = {
        "schema_version": SCHEMA, "world_id": "lantern_hollow",
        "start_scene": "quay", "step_limit": 12,
        "scenes": [
            {
                "id": "quay", "ending": None,
                "pickups": [{"id": "find_key", "item_id": "brass_key"}],
                "exits": [
                    {"id": "north", "to": "gate", "requires_item": "brass_key"},
                    {"id": "down", "to": "sinkhole", "requires_item": None},
                ],
            },
            {
                "id": "gate", "ending": None, "pickups": [],
                "exits": [
                    {"id": "inside", "to": "sanctuary", "requires_item": None},
                ],
            },
            {"id": "sanctuary", "ending": "victory", "pickups": [], "exits": []},
            {"id": "sinkhole", "ending": "failure", "pickups": [], "exits": []},
        ],
    }
    actions = [
        {"kind": "collect", "pickup_id": "find_key"},
        {"kind": "travel", "exit_id": "north"},
        {"kind": "travel", "exit_id": "inside"},
    ]
    return world, actions


def _json(text: str, label: str) -> Any:
    try:
        if len(text.encode("utf-8")) > MAX_JSON_BYTES:
            raise SceneTravelError(f"{label} exceeds 128 KiB")
        return json.loads(text)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, SceneTravelError):
            raise
        raise SceneTravelError(f"invalid {label} JSON") from exc


def parse_player_command(line: str) -> dict[str, str]:
    """Parse accessible local verbs or strict JSON without executing content."""
    if type(line) is not str:
        raise SceneTravelError("player command must be text")
    try:
        size = len(line.encode("utf-8"))
    except UnicodeError as exc:
        raise SceneTravelError("invalid player command encoding") from exc
    if size > MAX_JSON_BYTES:
        raise SceneTravelError("player command exceeds 128 KiB")
    value = line.strip()
    if value.startswith("{"):
        return _action(_json(value, "player action"))
    words = value.split()
    if len(words) == 2 and words[0] in ("collect", "travel"):
        field = "pickup_id" if words[0] == "collect" else "exit_id"
        return _action({"kind": words[0], field: words[1]})
    raise SceneTravelError("use collect PICKUP, travel EXIT or JSON")


def _emit(writer: Any, payload: dict[str, Any]) -> None:
    writer.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    writer.flush()


def _checkpoint(writer: Any, snapshot: dict[str, Any], reason: str) -> None:
    _emit(writer, {
        "event": "checkpoint", "reason": reason,
        "source_digest": snapshot["source_digest"],
        "state_digest": snapshot["state_digest"], "session": snapshot,
    })


def play_interactive(
    world: Any = None, *,
    session: Any = None,
    expected_source_digest: str | None = None,
    checkpoint_every: int = 8,
    input_stream: Any = None,
    output_stream: Any = None,
) -> dict[str, Any]:
    """Play an authored offline journey with verifiable resume checkpoints.

    EOF and repeated invalid input fail closed after emitting the latest
    valid checkpoint. The engine never reads or writes local files itself.
    """
    if (world is None) == (session is None):
        raise SceneTravelError("supply exactly one authored world or saved session")
    if type(checkpoint_every) is not int or not 1 <= checkpoint_every <= 64:
        raise SceneTravelError("checkpoint interval outside 1..64")
    snapshot = new_session(world) if session is None else verify_session(session)
    if expected_source_digest is not None:
        if (
            type(expected_source_digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_source_digest) is None
            or snapshot["source_digest"] != expected_source_digest
        ):
            raise SceneTravelError("source does not match trusted digest")
    reader = sys.stdin if input_stream is None else input_stream
    writer = sys.stdout if output_stream is None else output_stream
    _emit(writer, {
        "event": "started", "source_digest": snapshot["source_digest"],
        "state_digest": snapshot["state_digest"],
        "scene_id": snapshot["state"]["scene_id"],
    })
    while snapshot["state"]["phase"] == "active":
        scene = _scene(snapshot["world"], snapshot["state"]["scene_id"])
        available = [
            item for item in scene["pickups"]
            if scene["id"] + ":" + item["id"] not in snapshot["state"]["collected"]
        ]
        _emit(writer, {
            "event": "scene", "scene_id": scene["id"],
            "tick": snapshot["state"]["tick"],
            "exits": scene["exits"], "pickups": available,
            "inventory": snapshot["state"]["inventory"],
            "state_digest": snapshot["state_digest"],
            "commands": ["collect PICKUP", "travel EXIT"],
        })
        for attempt in range(3):
            line = reader.readline(MAX_JSON_BYTES + 1)
            if not line:
                _checkpoint(writer, snapshot, "input_eof")
                raise SceneTravelError(
                    "input ended before ending; verified checkpoint emitted"
                )
            try:
                action = parse_player_command(line)
                updated = _advance(snapshot, action)
            except SceneTravelError as exc:
                _emit(writer, {
                    "event": "rejected", "error": str(exc),
                    "remaining_retries": 2 - attempt,
                })
                if attempt == 2:
                    _checkpoint(writer, snapshot, "invalid_commands")
                    raise SceneTravelError(
                        "three invalid commands; verified checkpoint emitted"
                    ) from exc
            else:
                snapshot = updated
                _emit(writer, {
                    "event": "accepted", "action": action,
                    "tick": snapshot["state"]["tick"],
                    "state_digest": snapshot["state_digest"],
                })
                break
        if (
            snapshot["state"]["phase"] == "active"
            and snapshot["state"]["tick"] % checkpoint_every == 0
        ):
            _checkpoint(writer, snapshot, "interval")
    _checkpoint(writer, snapshot, "terminal")
    _emit(writer, {
        "event": "terminal", "phase": snapshot["state"]["phase"],
        "ending": snapshot["state"]["ending"],
        "scene_id": snapshot["state"]["scene_id"],
        "state_digest": snapshot["state_digest"],
    })
    return snapshot


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m skeleton.game.gameplay.scene_travel",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo")
    start = sub.add_parser("simulate")
    start.add_argument("--world-json", required=True)
    start.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--session-json", required=True)
    resume = sub.add_parser("resume")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    play = sub.add_parser("play")
    source = play.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--world-json")
    source.add_argument("--session-json")
    play.add_argument("--source-digest")
    play.add_argument("--checkpoint-every", type=int, default=8)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "play":
            world = (
                original_demo()[0] if args.demo else
                _json(args.world_json, "world")
                if args.world_json is not None else None
            )
            session = (
                _json(args.session_json, "session")
                if args.session_json is not None else None
            )
            play_interactive(
                world, session=session,
                expected_source_digest=args.source_digest,
                checkpoint_every=args.checkpoint_every,
            )
            return 0
        if args.command == "demo":
            world, actions = original_demo()
            result = simulate(world, actions)
        elif args.command == "simulate":
            result = simulate(
                _json(args.world_json, "world"),
                _json(args.actions_json, "actions"),
            )
        elif args.command == "verify":
            result = verify_session(_json(args.session_json, "session"))
        else:
            result = resume_session(
                _json(args.session_json, "session"),
                _json(args.actions_json, "actions"),
            )
    except SceneTravelError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
