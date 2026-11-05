"""Reproducible original tactical terrain with proven playable spawn corridor.

This generator emits canonical arena source, not rendered assets or provider
content. Seed and parameters are included in a replay-verifiable receipt.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from collections.abc import Sequence
from typing import Any

from skeleton.game.gameplay.flgb_gameplay_runtime import dig
from skeleton.game.gameplay.tactical_arena import (
    MAX_WALLS, normalize_arena, original_arena,
)
from skeleton.game.gameplay.arena_policy import run_autoplay
from skeleton.game.gameplay.turn_combat import (
    CombatSessionError, _id, _integer, _object, _parse_json,
)

SCHEMA = "skeleton.tactical_terrain.v1"
MAX_SEED = 2147483647


def _generator(raw: Any) -> dict[str, Any]:
    obj = _object(raw, {
        "schema_version", "seed", "world_id", "arena_id",
        "width", "height", "density", "turn_limit",
    }, "terrain generator")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported terrain generator schema")
    return {
        "schema_version": SCHEMA,
        "seed": _integer(obj["seed"], "seed", 0, MAX_SEED),
        "world_id": _id(obj["world_id"], "world_id"),
        "arena_id": _id(obj["arena_id"], "arena_id"),
        "width": _integer(obj["width"], "width", 4, 32),
        "height": _integer(obj["height"], "height", 3, 32),
        "density": _integer(obj["density"], "density", 0, 40),
        "turn_limit": _integer(obj["turn_limit"], "turn_limit", 4, 128),
    }


def _random(state: int) -> int:
    """32-bit xorshift with an explicit nonzero seed domain."""
    value = state or 0x6D2B79F5
    value ^= (value << 13) & 0xFFFFFFFF
    value ^= value >> 17
    value ^= (value << 5) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def _path(source: dict[str, Any]) -> list[list[int]]:
    """Find a shortest traversable actor-to-actor path without teleporting."""
    start = tuple(source["actors"][0]["position"])
    goal = tuple(source["actors"][1]["position"])
    walls = {tuple(p) for p in source["walls"]}
    queue = deque([start])
    previous: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            break
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            next_point = (x + dx, y + dy)
            if not (0 <= next_point[0] < source["width"]
                    and 0 <= next_point[1] < source["height"]):
                continue
            if next_point in walls or next_point in previous:
                continue
            previous[next_point] = (x, y)
            queue.append(next_point)
    if goal not in previous:
        raise CombatSessionError("generated terrain has no traversable actor route")
    route = []
    cursor: tuple[int, int] | None = goal
    while cursor is not None:
        route.append(list(cursor))
        cursor = previous[cursor]
    return list(reversed(route))


def generate_terrain(raw: Any) -> dict[str, Any]:
    spec = _generator(raw)
    width, height = spec["width"], spec["height"]
    lane = height // 2
    random_state = spec["seed"]
    walls = []
    for y in range(height):
        for x in range(width):
            random_state = _random(random_state)
            # The central corridor guarantees a physically reachable route.
            if y == lane or random_state % 100 >= spec["density"]:
                continue
            walls.append([x, y])
    if len(walls) > MAX_WALLS:
        walls = walls[:MAX_WALLS]
    arena = original_arena()
    arena.update({
        "world_id": spec["world_id"], "arena_id": spec["arena_id"],
        "width": width, "height": height, "walls": walls,
        "turn_limit": spec["turn_limit"],
    })
    arena["actors"][0]["position"] = [0, lane]
    arena["actors"][1]["position"] = [width - 1, lane]
    canonical = normalize_arena(arena)
    route = _path(canonical)
    result = {
        "schema_version": SCHEMA, "generator": spec,
        "generator_digest": dig(spec),
        "source": canonical, "source_digest": dig(canonical),
        "route": route, "route_digest": dig(route),
    }
    return result


def verify_terrain(payload: Any) -> dict[str, Any]:
    obj = _object(payload, {
        "schema_version", "generator", "generator_digest",
        "source", "source_digest", "route", "route_digest",
    }, "terrain receipt")
    if obj["schema_version"] != SCHEMA:
        raise CombatSessionError("unsupported terrain receipt schema")
    rebuilt = generate_terrain(obj["generator"])
    if rebuilt != obj:
        raise CombatSessionError("terrain generator or source receipt mismatch")
    return rebuilt


def preview_terrain(payload: Any) -> dict[str, Any]:
    generated = verify_terrain(payload)
    played = run_autoplay(generated["source"])
    return {
        "schema_version": SCHEMA,
        "source_digest": generated["source_digest"],
        "generator_digest": generated["generator_digest"],
        "route_digest": generated["route_digest"],
        "phase": played["state"]["phase"],
        "state_digest": played["state_digest"],
        "session": played,
    }


def original_terrain() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA, "seed": 311,
        "world_id": "lantern_harbor", "arena_id": "tide_maze",
        "width": 9, "height": 5, "density": 24, "turn_limit": 48,
    }


def cli(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m skeleton arena-terrain")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Generate original offline canal terrain")
    gen = sub.add_parser("generate")
    gen.add_argument("--generator-json", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--terrain-json", required=True)
    preview = sub.add_parser("preview")
    preview.add_argument("--terrain-json", required=True)
    args = parser.parse_args(list(argv))
    try:
        if args.command == "demo":
            result = generate_terrain(original_terrain())
        elif args.command == "generate":
            result = generate_terrain(_parse_json(args.generator_json, "terrain source"))
        elif args.command == "verify":
            result = verify_terrain(_parse_json(args.terrain_json, "terrain receipt"))
        else:
            result = preview_terrain(_parse_json(args.terrain_json, "terrain receipt"))
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except (CombatSessionError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(cli(sys.argv[1:]))
