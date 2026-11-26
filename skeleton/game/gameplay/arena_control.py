"""Deterministic offline control-point tactical arena, replay and portable saves.

The canonical tactical arena owns movement, collision, attacks and turn order.
This mode awards capture points only from positions reached by those verified
canonical actions. JSON digests are integrity checks, never signatures.
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
from skeleton.game.gameplay.tactical_arena import (
    _action as arena_action, _advance as arena_advance, _point,
    new_arena, normalize_arena, original_arena,
)
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.arena_control.v1"
PACKAGE_SCHEMA = "skeleton.arena_control_package.v1"
MAX_ZONES = 8
MAX_ACTIONS = 96
MAX_BYTES = 2 * 1024 * 1024


def _encoded(value: Any) -> str:
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise CombatSessionError("invalid control-point export") from exc
    if len(result.encode("utf-8")) > MAX_BYTES:
        raise CombatSessionError("control-point export exceeds 2 MiB")
    return result


def normalize_control(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "control_id", "arena", "zones",
        "score_target", "max_actions",
    }, "control-point source")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported control-point source schema")
    control_id = _id(obj["control_id"], "control_id")
    arena = normalize_arena(obj["arena"])
    teams = {actor["team"] for actor in arena["actors"]}
    if len(teams) < 2:
        raise CombatSessionError("control-point game requires opposing teams")
    zones_raw = obj["zones"]
    if type(zones_raw) is not list or not 1 <= len(zones_raw) <= MAX_ZONES:
        raise CombatSessionError("invalid control-point zone count")
    zones: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_positions: set[tuple[int, int]] = set()
    walls = {tuple(point) for point in arena["walls"]}
    for entry in zones_raw:
        item = _object(entry, {"id", "position", "points"}, "control-point zone")
        zone_id = _id(item["id"], "zone_id")
        position = _point(item["position"], "zone", arena["width"], arena["height"])
        if zone_id in seen_ids or position in seen_positions:
            raise CombatSessionError("duplicate control-point zone")
        if position in walls:
            raise CombatSessionError("control-point zone lies inside a wall")
        seen_ids.add(zone_id)
        seen_positions.add(position)
        zones.append({
            "id": zone_id, "position": list(position),
            "points": _integer(item["points"], "zone points", 1, 5),
        })
    zones.sort(key=lambda zone: zone["id"])
    score_target = _integer(obj["score_target"], "score_target", 1, 200)
    max_actions = _integer(obj["max_actions"], "max_actions", 1, MAX_ACTIONS)
    if max_actions > arena["turn_limit"]:
        raise CombatSessionError("control-point action budget exceeds arena turns")
    source = {
        "schema_version": SCHEMA, "control_id": control_id,
        "arena": arena, "zones": zones,
        "score_target": score_target, "max_actions": max_actions,
    }
    _encoded(source)
    return source


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["arena"]["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def _event_digest(journal: list[dict[str, Any]]) -> str:
    events = tuple(
        GameplayEvent(i, "arena.control.capture",
                      event["action"]["actor_id"], event["receipt"])
        for i, event in enumerate(journal)
    )
    return EventBus(events).digest


def new_control(raw: Any) -> dict[str, Any]:
    source = normalize_control(raw)
    arena = new_arena(source["arena"])
    state = {
        "tick": 0, "phase": "active", "winner": None,
        "scores": {
            team: 0 for team in sorted({a["team"] for a in source["arena"]["actors"]})
        },
        "captures": [],
    }
    return {
        "schema_version": SCHEMA, "source": source,
        "source_digest": dig(source), "arena_session": arena,
        "state": state, "state_digest": dig(state),
        "journal": [], "event_bus_digest": EventBus().digest,
        "save": _save(source, state),
    }


def _advance_control(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, previous = snapshot["source"], snapshot["state"]
    if previous["phase"] != "active":
        raise CombatSessionError("control-point game is terminal")
    if previous["tick"] >= source["max_actions"]:
        raise CombatSessionError("control-point action budget exhausted")
    action = arena_action(raw)
    played = arena_advance(snapshot["arena_session"], action)
    state = {
        "tick": previous["tick"] + 1, "phase": "active", "winner": None,
        "scores": dict(previous["scores"]),
        "captures": list(previous["captures"]),
    }
    living = {
        tuple(actor["position"]): source_actor["team"]
        for source_actor in source["arena"]["actors"]
        for actor in [played["state"]["actors"][source_actor["id"]]]
        if actor["hp"] > 0
    }
    captures = []
    for zone in source["zones"]:
        team = living.get(tuple(zone["position"]))
        if team is None:
            continue
        state["scores"][team] += zone["points"]
        capture = {
            "tick": state["tick"], "zone_id": zone["id"],
            "team": team, "points": zone["points"],
        }
        state["captures"].append(capture)
        captures.append(capture)
    leaders = [
        team for team, points in state["scores"].items()
        if points >= source["score_target"]
    ]
    if leaders:
        state["phase"] = "won" if len(leaders) == 1 else "draw"
        state["winner"] = leaders[0] if len(leaders) == 1 else None
    elif played["state"]["phase"] != "active":
        state["phase"] = played["state"]["phase"]
        state["winner"] = played["state"]["winner"]
    elif state["tick"] == source["max_actions"]:
        state["phase"] = "draw"
    event = {
        "sequence": previous["tick"], "action": action,
        "before": snapshot["state_digest"], "after": dig(state),
        "arena_state_digest": played["state_digest"],
        "captures": captures,
    }
    event["receipt"] = dig(event)
    journal = [*snapshot["journal"], event]
    result = {
        "schema_version": SCHEMA, "source": source,
        "source_digest": snapshot["source_digest"], "arena_session": played,
        "state": state, "state_digest": dig(state),
        "journal": journal, "event_bus_digest": _event_digest(journal),
        "save": _save(source, state, snapshot["save"]),
    }
    _encoded(result)
    return result


def verify_control(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "source", "source_digest", "arena_session",
        "state", "state_digest", "journal", "event_bus_digest", "save",
    }, "control-point checkpoint")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported control-point checkpoint schema")
    _encoded(obj)
    rebuilt = new_control(obj["source"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > rebuilt["source"]["max_actions"]:
        raise CombatSessionError("invalid control-point journal length")
    for entry in journal:
        if type(entry) is not dict or "action" not in entry:
            raise CombatSessionError("invalid control-point journal entry")
        rebuilt = _advance_control(rebuilt, entry["action"])
        if rebuilt["journal"][-1] != entry:
            raise CombatSessionError("control-point event receipt mismatch")
    if rebuilt != obj:
        raise CombatSessionError("control-point replay or save lineage mismatch")
    return rebuilt


def resume_control(raw: Any, actions: Any) -> dict[str, Any]:
    checkpoint = verify_control(raw)
    if type(actions) is not list:
        raise CombatSessionError("invalid control-point actions")
    if len(actions) + len(checkpoint["journal"]) > checkpoint["source"]["max_actions"]:
        raise CombatSessionError("control-point action budget exceeded")
    for action in actions:
        checkpoint = _advance_control(checkpoint, action)
    return checkpoint


def play_control(source: Any, actions: Any) -> dict[str, Any]:
    return resume_control(new_control(source), actions)


def package_control(raw: Any) -> dict[str, Any]:
    checkpoint = verify_control(raw)
    manifest = {
        "world_id": checkpoint["source"]["arena"]["world_id"],
        "control_id": checkpoint["source"]["control_id"],
        "source_digest": checkpoint["source_digest"],
        "state_digest": checkpoint["state_digest"],
        "arena_state_digest": checkpoint["arena_session"]["state_digest"],
        "event_bus_digest": checkpoint["event_bus_digest"],
        "save_digest": dig(checkpoint["save"]),
        "tick": checkpoint["state"]["tick"],
        "phase": checkpoint["state"]["phase"],
        "winner": checkpoint["state"]["winner"],
        "scores": checkpoint["state"]["scores"],
    }
    result = {
        "schema_version": PACKAGE_SCHEMA,
        "snapshot": checkpoint, "manifest": manifest,
        "claim": "integrity_checked_offline_save",
    }
    result["receipt"] = dig(result)
    _encoded(result)
    return result


def verify_control_package(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "snapshot", "manifest", "claim", "receipt",
    }, "control-point package")
    if obj["schema_version"] != PACKAGE_SCHEMA or obj["claim"] != "integrity_checked_offline_save":
        raise CombatSessionError("unsupported control-point package")
    _encoded(obj)
    expected = package_control(obj["snapshot"])
    if expected != obj:
        raise CombatSessionError("control-point package or replay mismatch")
    return expected


def original_control() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "control_id": "lantern_canal_control",
        "arena": original_arena(),
        "zones": [
            {"id": "west_beacon", "position": [1, 1], "points": 1},
            {"id": "east_beacon", "position": [5, 1], "points": 1},
        ],
        "score_target": 2, "max_actions": 12,
    }


def original_actions() -> list[dict[str, Any]]:
    return [
        {"kind": "move", "actor_id": "scout", "direction": "east"},
        {"kind": "move", "actor_id": "warden", "direction": "west"},
        {"kind": "guard", "actor_id": "scout"},
    ]


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-control")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play original offline beacon capture")
    start = sub.add_parser("new", help="Create deterministic source-bound checkpoint")
    start.add_argument("--source-json", required=True)
    play = sub.add_parser("play", help="Apply bounded tactical actions")
    play.add_argument("--source-json", required=True)
    play.add_argument("--actions-json", required=True)
    resume = sub.add_parser("resume", help="Resume verified control-point checkpoint")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify", help="Replay-verify a control-point checkpoint")
    verify.add_argument("--session-json", required=True)
    pack = sub.add_parser("pack", help="Export portable replay-verified checkpoint")
    pack.add_argument("--session-json", required=True)
    unpack = sub.add_parser("unpack", help="Verify portable control-point checkpoint")
    unpack.add_argument("--package-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = play_control(original_control(), original_actions())
        elif args.command == "new":
            result = new_control(_parse_json(args.source_json, "control-point source"))
        elif args.command == "play":
            result = play_control(
                _parse_json(args.source_json, "control-point source"),
                _parse_json(args.actions_json, "control-point actions"),
            )
        elif args.command == "resume":
            result = resume_control(
                _parse_json(args.session_json, "control-point checkpoint"),
                _parse_json(args.actions_json, "control-point actions"),
            )
        elif args.command == "verify":
            result = verify_control(_parse_json(args.session_json, "control-point checkpoint"))
        elif args.command == "pack":
            result = package_control(_parse_json(args.session_json, "control-point checkpoint"))
        else:
            result = verify_control_package(_parse_json(args.package_json, "control-point package"))
        print(_encoded(result))
        return 0
    except (CombatSessionError, KeyError, TypeError, ValueError, RecursionError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
