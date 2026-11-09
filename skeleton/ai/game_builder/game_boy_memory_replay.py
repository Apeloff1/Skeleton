"""Reference-independent deterministic expected Game Boy hardware replay.

This plan records every *expected hardware RAM state* from the original game's
validated safe route, not from the native assembler implementation. It lets a
real GB emulator detect engine defects a header-valid ROM cannot reveal.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from .playable_world import PlayableWorld

_ACTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
_MAX_ACTIONS = 20_000
_SCHEMA = "skeleton.game_builder.game_boy_memory_replay.v1"


class GameBoyReplayError(ValueError):
    """Invalid reference trajectory or unachievable game-state transition."""


def plan_game_boy_memory_replay(world: PlayableWorld) -> dict[str, Any]:
    """Compute hardware-facing memory expectations for all solved levels."""
    if not isinstance(world, PlayableWorld):
        raise GameBoyReplayError("typed PlayableWorld required")
    if sum(len(level.safe_solution) for level in world.levels) > _MAX_ACTIONS:
        raise GameBoyReplayError("hardware replay step budget exceeded")
    initial_health = world.intent.starting_health
    score = 0
    steps = []
    for i, level in enumerate(world.levels):
        x, y = level.start
        acquired: set[tuple[int, int]] = set()
        for action in level.safe_solution:
            dx, dy = _ACTIONS[action]
            x, y = x + dx, y + dy
            if not (0 <= y < len(level.rows) and 0 <= x < len(level.rows[0])):
                raise GameBoyReplayError("replay attempts to cross hardware map boundary")
            tile = level.rows[y][x]
            if tile in "#H":
                raise GameBoyReplayError("safe replay crosses original wall or hazard")
            if tile == "C" and (x, y) not in acquired:
                acquired.add((x, y))
                score += 1
            remaining = len(level.collectibles) - len(acquired)
            won = i == len(world.levels) - 1 and (x, y) == level.exit and not remaining
            next_level = i < len(world.levels) - 1 and (x, y) == level.exit and not remaining
            if next_level:
                next_level_data = world.levels[i + 1]
                after_level = i + 1
                after_x, after_y = next_level_data.start
                after_remaining = len(next_level_data.collectibles)
            else:
                after_level = i
                after_x, after_y, after_remaining = x, y, remaining
            steps.append({
                "button": action,
                "level": after_level,
                "x": after_x, "y": after_y,
                "health": initial_health,
                "score": score,
                "gems_remaining": after_remaining,
                "won": int(won),
                "lost": 0,
            })
        if (x, y) != level.exit or len(acquired) != len(level.collectibles):
            raise GameBoyReplayError("reference route does not finish level")
    if not steps or steps[-1]["won"] != 1:
        raise GameBoyReplayError("reference never wins the original homebrew")
    result = {
        "schema": _SCHEMA,
        "world_digest": world.digest,
        "levels": len(world.levels),
        "starting_health": initial_health,
        "initial": {
            "level": 0,
            "x": world.levels[0].start[0],
            "y": world.levels[0].start[1],
            "health": initial_health,
            "score": 0,
            "gems_remaining": len(world.levels[0].collectibles),
            "won": 0,
            "lost": 0,
        },
        "steps": steps,
        "binary_compiled": False,
        "emulator_executed": False,
        "hardware_verified": False,
        "release_approved": False,
    }
    result["route_sha256"] = sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def export_game_boy_memory_replay(world: PlayableWorld, dest: Path) -> Path:
    if dest.is_symlink() or dest.exists():
        raise FileExistsError(str(dest))
    result = plan_game_boy_memory_replay(world)
    with dest.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return dest
