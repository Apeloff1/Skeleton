"""Independent reference for a real 8086 DOS game and its BIOS keyboard trace.

This oracle executes the original platform-neutral gameplay model, not the
generated DOS machine code. The separate CPU emulator must produce identical
RAM, HUD and player-position states without any guest memory modifications.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .playable_world import PlayableWorld
from .playable_simulation import initial_state, advance

_SCHEMA = "skeleton.game_builder.dos_8086_reference_replay.v1"
_MAX_KEYS = 20_000


class DOSReplayError(ValueError):
    """The original DOS game replay is invalid or outside bounded semantics."""


def reference_dos_replay(world: PlayableWorld) -> dict[str, object]:
    if not isinstance(world, PlayableWorld):
        raise DOSReplayError("typed original PlayableWorld required")
    moves = tuple(key for level in world.levels for key in level.safe_solution)
    if not moves or len(moves) > _MAX_KEYS:
        raise DOSReplayError("DOS native replay has invalid bounded key count")
    state = initial_state(world, authorized=True)

    def snapshot(key: str | None) -> dict[str, object]:
        return {
            "key": key,
            "level": state.level_index,
            "x": state.x, "y": state.y,
            "health": state.health, "score": state.score,
            "gems_remaining": len(world.levels[state.level_index].collectibles) - len(state.collected),
            "won": int(state.status == "won"),
            "lost": int(state.status == "lost"),
        }

    initial = snapshot(None)
    steps = []
    for direction in moves:
        state = advance(world, state, direction, authorized=True)
        steps.append(snapshot(direction))
    if state.status != "won":
        raise DOSReplayError("the original reference did not win")
    result = {
        "schema": _SCHEMA, "world_digest": world.digest,
        "levels": len(world.levels),
        "initial": initial,
        "steps": steps,
        "binary_compiled": False,
        "cpu_emulator_executed": False,
        "physical_hardware_verified": False,
        "redistribution_licensed": False,
    }
    result["trace_sha256"] = sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


def export_dos_replay(world: PlayableWorld, target: str | Path) -> Path:
    path = Path(target)
    if path.exists() or path.is_symlink():
        raise FileExistsError(str(path))
    result = reference_dos_replay(world)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return path
