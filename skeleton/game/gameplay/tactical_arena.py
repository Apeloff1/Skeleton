"""Offline source-bound tactical arena with real movement, cover and combat.

This is a bounded, deterministic turn simulation, not a rendering engine or
trusted asset-signature verifier. No network, dynamic code or provider calls.
All game saves are replayed from the immutable authored source before use.
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
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, MAX_CLI_BYTES, _id, _integer, _object,
    _parse_json, normalize_scenario,
)

SCHEMA = "skeleton.tactical_arena.v1"
MAX_WIDTH = 32
MAX_HEIGHT = 32
MAX_WALLS = 512
MAX_TURNS = 256
MAX_RANGE = 8


def _point(raw: Any, name: str, width: int, height: int) -> tuple[int, int]:
    if type(raw) is not list or len(raw) != 2:
        raise CombatSessionError(f"invalid {name} coordinate")
    x = _integer(raw[0], f"{name}.x", 0, width - 1)
    y = _integer(raw[1], f"{name}.y", 0, height - 1)
    return x, y


def normalize_arena(raw: Any) -> dict[str, Any]:
    """Canonicalize complete authored geometry and actor stats before play."""
    obj = _object(raw, {
        "schema_version", "world_id", "arena_id", "width", "height",
        "walls", "actors", "turn_limit",
    }, "arena")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported arena schema")
    world_id = _id(obj["world_id"], "world_id")
    arena_id = _id(obj["arena_id"], "arena_id")
    width = _integer(obj["width"], "width", 2, MAX_WIDTH)
    height = _integer(obj["height"], "height", 2, MAX_HEIGHT)
    turn_limit = _integer(obj["turn_limit"], "turn_limit", 1, MAX_TURNS)
    walls = obj["walls"]
    if type(walls) is not list or len(walls) > min(MAX_WALLS, width * height - 2):
        raise CombatSessionError("invalid wall budget")
    wall_points = [_point(w, "wall", width, height) for w in walls]
    if len(set(wall_points)) != len(wall_points):
        raise CombatSessionError("duplicate wall coordinate")
    wall_set = set(wall_points)
    raw_actors = obj["actors"]
    if type(raw_actors) is not list:
        raise CombatSessionError("invalid arena actors")
    base_actors = []
    for item in raw_actors:
        if type(item) is not dict:
            raise CombatSessionError("invalid arena actor")
        _object(item, {
            "id", "team", "max_hp", "attack", "defense", "speed",
            "position", "range",
        }, "arena actor")
        base_actors.append({key: item[key] for key in (
            "id", "team", "max_hp", "attack", "defense", "speed"
        )})
    canonical = normalize_scenario({
        "schema_version": "skeleton.turn_combat.v1",
        "world_id": world_id, "encounter_id": arena_id,
        "actors": base_actors, "turn_limit": turn_limit,
    })
    by_id = {actor["id"]: actor for actor in canonical["actors"]}
    occupied: set[tuple[int, int]] = set()
    actors = []
    for item in raw_actors:
        actor_id = _id(item["id"], "actor_id")
        position = _point(item["position"], "actor", width, height)
        if position in wall_set or position in occupied:
            raise CombatSessionError("actor spawn blocked or duplicated")
        occupied.add(position)
        actors.append({
            **by_id[actor_id],
            "position": list(position),
            "range": _integer(item["range"], "range", 1, MAX_RANGE),
        })
    actors.sort(key=lambda actor: actor["id"])
    return {
        "schema_version": SCHEMA, "world_id": world_id, "arena_id": arena_id,
        "width": width, "height": height, "turn_limit": turn_limit,
        "walls": [list(p) for p in sorted(wall_set)], "actors": actors,
    }


def _save(source: dict[str, Any], state: dict[str, Any],
          parent: dict[str, Any] | None = None) -> dict[str, Any]:
    return dict(SaveableGameplayState(
        world_id=source["world_id"], schema_version=1,
        tick=state["tick"], state_digest=dig(state),
        canon_digest=dig(source),
        parent_save_digest=dig(parent) if parent is not None else None,
    ).__dict__)


def new_arena(source: Any) -> dict[str, Any]:
    spec = normalize_arena(source)
    state = {
        "tick": 0, "phase": "active", "winner": None, "next_index": 0,
        "actors": {
            a["id"]: {
                "hp": a["max_hp"], "guard": False,
                "position": list(a["position"]),
            } for a in spec["actors"]
        },
    }
    return {
        "schema_version": SCHEMA, "source": spec,
        "source_digest": dig(spec), "state": state,
        "state_digest": dig(state), "journal": [],
        "event_bus_digest": EventBus().digest,
        "save": _save(spec, state),
    }


def _order(source: dict[str, Any]) -> list[str]:
    return [a["id"] for a in sorted(
        source["actors"], key=lambda a: (-a["speed"], a["id"])
    )]


def _active(source: dict[str, Any], state: dict[str, Any]) -> tuple[str, int]:
    order = _order(source)
    for offset in range(len(order)):
        index = (state["next_index"] + offset) % len(order)
        actor_id = order[index]
        if state["actors"][actor_id]["hp"] > 0:
            return actor_id, index
    raise CombatSessionError("arena has no active actor")


def _action(raw: Any) -> dict[str, Any]:
    if type(raw) is not dict:
        raise CombatSessionError("invalid arena action")
    kind = raw.get("kind")
    keys = {
        "move": {"kind", "actor_id", "direction"},
        "attack": {"kind", "actor_id", "target_id"},
        "guard": {"kind", "actor_id"},
        "rest": {"kind", "actor_id"},
    }
    if type(kind) is not str or kind not in keys:
        raise CombatSessionError("unsupported arena action")
    _object(raw, keys[kind], "arena action")
    result = {"kind": kind, "actor_id": _id(raw["actor_id"], "actor_id")}
    if kind == "move":
        if type(raw["direction"]) is not str or raw["direction"] not in (
            "north", "south", "west", "east"
        ):
            raise CombatSessionError("invalid move direction")
        result["direction"] = raw["direction"]
    elif kind == "attack":
        result["target_id"] = _id(raw["target_id"], "target_id")
    return result


def _occupied(source: dict[str, Any], state: dict[str, Any]) -> set[tuple[int, int]]:
    walls = {tuple(p) for p in source["walls"]}
    actors = {
        tuple(s["position"]) for s in state["actors"].values() if s["hp"] > 0
    }
    return walls | actors


def legal_moves(source: dict[str, Any], state: dict[str, Any],
                actor_id: str) -> list[str]:
    """Return directions in fixed order, respecting bounds and occupied tiles."""
    actor = state["actors"][actor_id]
    if actor["hp"] == 0:
        return []
    x, y = actor["position"]
    occupied = _occupied(source, state)
    directions = (
        ("north", 0, -1), ("east", 1, 0),
        ("south", 0, 1), ("west", -1, 0),
    )
    return [
        name for name, dx, dy in directions
        if 0 <= x + dx < source["width"]
        and 0 <= y + dy < source["height"]
        and (x + dx, y + dy) not in occupied
    ]


def _visible(source: dict[str, Any], state: dict[str, Any],
             attacker: str, target: str) -> bool:
    stats = {a["id"]: a for a in source["actors"]}
    x, y = state["actors"][attacker]["position"]
    tx, ty = state["actors"][target]["position"]
    distance = abs(x - tx) + abs(y - ty)
    if not 1 <= distance <= stats[attacker]["range"]:
        return False
    # Orthogonal rays only. Both walls and living intervening actors block.
    if x != tx and y != ty:
        return False
    step_x = (tx > x) - (tx < x)
    step_y = (ty > y) - (ty < y)
    blockers = _occupied(source, state)
    for step in range(1, distance):
        if (x + step * step_x, y + step * step_y) in blockers:
            return False
    return True


def legal_targets(source: dict[str, Any], state: dict[str, Any],
                  actor_id: str) -> list[str]:
    stats = {a["id"]: a for a in source["actors"]}
    if state["actors"][actor_id]["hp"] == 0:
        return []
    return sorted(
        other for other in stats
        if stats[other]["team"] != stats[actor_id]["team"]
        and state["actors"][other]["hp"] > 0
        and _visible(source, state, actor_id, other)
    )


def _event_digest(journal: list[dict[str, Any]]) -> str:
    events = tuple(
        GameplayEvent(i, "arena.action", event["action"]["actor_id"], event["receipt"])
        for i, event in enumerate(journal)
    )
    return EventBus(events).digest


def _advance(snapshot: dict[str, Any], raw: Any) -> dict[str, Any]:
    source, old = snapshot["source"], snapshot["state"]
    if old["phase"] != "active":
        raise CombatSessionError("arena is terminal")
    action = _action(raw)
    actor_id, index = _active(source, old)
    if actor_id != action["actor_id"]:
        raise CombatSessionError("out-of-turn arena actor")
    stats = {a["id"]: a for a in source["actors"]}
    state = {
        "tick": old["tick"] + 1, "phase": "active", "winner": None,
        "next_index": (index + 1) % len(stats),
        "actors": {k: {**v, "position": list(v["position"])}
                   for k, v in old["actors"].items()},
    }
    kind = action["kind"]
    if kind == "move":
        direction = action["direction"]
        if direction not in legal_moves(source, old, actor_id):
            raise CombatSessionError("movement blocked")
        dx, dy = {
            "north": (0, -1), "south": (0, 1),
            "east": (1, 0), "west": (-1, 0),
        }[direction]
        state["actors"][actor_id]["position"][0] += dx
        state["actors"][actor_id]["position"][1] += dy
    elif kind == "attack":
        target = action["target_id"]
        if target not in legal_targets(source, old, actor_id):
            raise CombatSessionError("target out of range or line of sight")
        damage = max(1, stats[actor_id]["attack"] - stats[target]["defense"])
        if state["actors"][target]["guard"]:
            damage = max(1, damage // 2)
            state["actors"][target]["guard"] = False
        state["actors"][target]["hp"] = max(
            0, state["actors"][target]["hp"] - damage
        )
    elif kind == "guard":
        state["actors"][actor_id]["guard"] = True
    else:
        state["actors"][actor_id]["hp"] = min(
            stats[actor_id]["max_hp"], state["actors"][actor_id]["hp"] + 2
        )
    alive = {
        stats[key]["team"] for key, value in state["actors"].items()
        if value["hp"] > 0
    }
    if len(alive) == 1:
        state["phase"] = "won"
        state["winner"] = next(iter(alive))
    elif state["tick"] >= source["turn_limit"]:
        state["phase"] = "draw"
    event = {
        "sequence": old["tick"], "action": action,
        "before": snapshot["state_digest"], "after": dig(state),
    }
    event["receipt"] = dig(event)
    journal = [*snapshot["journal"], event]
    return {
        "schema_version": SCHEMA, "source": source,
        "source_digest": snapshot["source_digest"], "state": state,
        "state_digest": dig(state), "journal": journal,
        "event_bus_digest": _event_digest(journal),
        "save": _save(source, state, snapshot["save"]),
    }


def verify_arena(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {
        "schema_version", "source", "source_digest", "state",
        "state_digest", "journal", "event_bus_digest", "save",
    }, "arena session")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported arena save schema")
    rebuilt = new_arena(obj["source"])
    journal = obj["journal"]
    if type(journal) is not list or len(journal) > rebuilt["source"]["turn_limit"]:
        raise CombatSessionError("invalid arena journal budget")
    for event in journal:
        if type(event) is not dict or "action" not in event:
            raise CombatSessionError("invalid arena journal entry")
        rebuilt = _advance(rebuilt, event["action"])
        if rebuilt["journal"][-1] != event:
            raise CombatSessionError("arena replay mismatch")
    if rebuilt != obj:
        raise CombatSessionError("arena snapshot or save lineage mismatch")
    return rebuilt


def resume_arena(payload: Any, actions: Any) -> dict[str, Any]:
    session = verify_arena(payload)
    if type(actions) is not list:
        raise CombatSessionError("invalid arena action batch")
    if len(actions) + len(session["journal"]) > session["source"]["turn_limit"]:
        raise CombatSessionError("arena action budget exceeded")
    for action in actions:
        session = _advance(session, action)
    return session


def simulate_arena(source: Any, actions: Any) -> dict[str, Any]:
    return resume_arena(new_arena(source), actions)


def original_arena() -> dict[str, Any]:
    """Original Lantern Harbor canal crossing, with two tactical sight lanes."""
    return {
        "schema_version": SCHEMA, "world_id": "lantern_harbor",
        "arena_id": "canal_crossing", "width": 7, "height": 3,
        "turn_limit": 24, "walls": [[3, 0], [3, 2]],
        "actors": [
            {"id": "scout", "team": "wayfarers", "max_hp": 14,
             "attack": 5, "defense": 2, "speed": 3,
             "position": [0, 1], "range": 2},
            {"id": "warden", "team": "reedbound", "max_hp": 8,
             "attack": 3, "defense": 1, "speed": 2,
             "position": [6, 1], "range": 1},
        ],
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton combat-arena")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Play original offline arena with deterministic AI")
    play = sub.add_parser("play", help="Play interactive JSON-line tactical turns")
    play.add_argument("--demo", action="store_true")
    play.add_argument("--source-json")
    play.add_argument("--resume-json")
    play.add_argument("--auto-team", action="append", default=[])
    auto = sub.add_parser("auto", help="Autoplay an authored tactical arena")
    auto.add_argument("--source-json", required=True)
    sim = sub.add_parser("simulate", help="Apply source-bound player commands")
    sim.add_argument("--source-json", required=True)
    sim.add_argument("--actions-json", required=True)
    verify = sub.add_parser("verify", help="Replay-check exported arena save")
    verify.add_argument("--session-json", required=True)
    inspect = sub.add_parser("inspect", help="Replay-derived tactical timeline")
    inspect.add_argument("--session-json", required=True)
    compare = sub.add_parser("compare", help="Compare two source-bound arena branches")
    compare.add_argument("--left-json", required=True)
    compare.add_argument("--right-json", required=True)
    resume = sub.add_parser("resume", help="Resume a verified arena save")
    resume.add_argument("--session-json", required=True)
    resume.add_argument("--actions-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command in ("inspect", "compare"):
            from skeleton.game.gameplay.arena_inspector import (
                inspect_session, compare_sessions,
            )
            result = (
                inspect_session(_parse_json(args.session_json, "arena save"))
                if args.command == "inspect" else compare_sessions(
                    _parse_json(args.left_json, "left arena save"),
                    _parse_json(args.right_json, "right arena save"),
                )
            )
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "play":
            from skeleton.game.gameplay.arena_interactive import play_arena
            if sum(bool(x) for x in (
                args.demo, args.source_json, args.resume_json
            )) != 1:
                raise CombatSessionError("play needs exactly one source or resume")
            saved = _parse_json(args.resume_json, "arena save") if args.resume_json else None
            authored = (
                saved.get("source") if type(saved) is dict else None
            ) if saved is not None else (
                original_arena() if args.demo else _parse_json(args.source_json, "arena source")
            )
            play_arena(authored, resume=saved, auto_teams=args.auto_team)
            return 0
        if args.command in ("demo", "auto"):
            from skeleton.game.gameplay.arena_policy import run_autoplay
            source = original_arena() if args.command == "demo" else _parse_json(
                args.source_json, "arena source"
            )
            result = run_autoplay(source)
        elif args.command == "simulate":
            result = simulate_arena(
                _parse_json(args.source_json, "arena source"),
                _parse_json(args.actions_json, "arena actions"),
            )
        elif args.command == "verify":
            result = verify_arena(_parse_json(args.session_json, "arena save"))
        else:
            result = resume_arena(
                _parse_json(args.session_json, "arena save"),
                _parse_json(args.actions_json, "arena actions"),
            )
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 2 * 1024 * 1024:
            raise CombatSessionError("arena output budget exceeded")
        print(encoded)
        return 0
    except (CombatSessionError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
