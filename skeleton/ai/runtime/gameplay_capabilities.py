"""Procedural, deterministic, model-free 2D game-building primitives.

Tiles are one cell across, origin is top left, positive y points downward.
Walls are '#', traversable floor '.', spawn 'S', and goal 'G'.
These operations compile and simulate an original abstract game scene,
not a ROM, proprietary console format or modern game-engine binary.

All functions are pure, bounded and deterministic. They create no files,
models, network requests, training examples or authority grants.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
from typing import Any

MIN_DIM = 5
MAX_DIM = 32
MAX_FRAMES = 64
MAX_SPEED = 4
_TILES = frozenset("#.SG")


class GameplayError(ValueError):
    """Invalid, over-budget or inconsistent local gameplay input."""


def _integer(value: Any, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise GameplayError("gameplay integer outside admitted limits")
    return value


def _fields(value: Any, names: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != names:
        raise GameplayError("gameplay argument schema mismatch")
    return value


def _map(value: Any) -> tuple[tuple[str, ...], tuple[int, int], tuple[int, int]]:
    if (
        not isinstance(value, list) or not MIN_DIM <= len(value) <= MAX_DIM
        or any(not isinstance(row, str) for row in value)
    ):
        raise GameplayError("level must be 5-32 rows of tile strings")
    width = len(value[0])
    if not MIN_DIM <= width <= MAX_DIM:
        raise GameplayError("level must be 5-32 columns")
    if any(len(row) != width or set(row) - _TILES for row in value):
        raise GameplayError("level must have equal-width admitted tile characters")
    spawn, goal = [], []
    for y, line in enumerate(value):
        for x, tile in enumerate(line):
            if tile == "S":
                spawn.append((x, y))
            elif tile == "G":
                goal.append((x, y))
    if len(spawn) != 1 or len(goal) != 1:
        raise GameplayError("level requires exactly one spawn and one goal")
    return tuple(value), spawn[0], goal[0]


def _traversable(rows: tuple[str, ...], x: int, y: int) -> bool:
    return (
        0 <= y < len(rows) and 0 <= x < len(rows[0])
        and rows[y][x] != "#"
    )


def _flood(
    rows: tuple[str, ...], start: tuple[int, int], goal: tuple[int, int],
) -> tuple[int | None, int]:
    queue = deque([start])
    steps: dict[tuple[int, int], int] = {start: 0}
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)):
            if _traversable(rows, nx, ny) and (nx, ny) not in steps:
                steps[nx, ny] = steps[(x, y)] + 1
                queue.append((nx, ny))
    return steps.get(goal), len(steps)


def _point(pair: tuple[int, int]) -> dict[str, int]:
    return {"x": pair[0], "y": pair[1]}


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True,
                   allow_nan=False, separators=(",", ":")).encode("ascii")
    ).hexdigest()


def compile_level(arguments: dict[str, Any]) -> dict[str, Any]:
    """Compile an engine-neutral map and report reachability and bounds."""
    args = _fields(arguments, {"tiles"})
    rows, spawn, goal = _map(args["tiles"])
    distance, visited = _flood(rows, spawn, goal)
    solids = sum(line.count("#") for line in rows)
    return {
        "schema_version": "skeleton.gameplay.level.v1",
        "width": len(rows[0]),
        "height": len(rows),
        "tiles": list(rows),
        "spawn": _point(spawn),
        "goal": _point(goal),
        "solid_count": solids,
        "walkable_count": len(rows) * len(rows[0]) - solids,
        "reachable_from_spawn": visited,
        "goal_reachable": distance is not None,
        "shortest_goal_steps": distance,
        "tile_digest": _digest(list(rows)),
        "proprietary_assets_embedded": False,
        "training_examples_added": 0,
    }


def compile_native_scene(arguments: dict[str, Any]) -> dict[str, Any]:
    """Compile a portable *engine-neutral* 2D scene with packed wall spans.

    The output is structured geometry/actors, never generated source code,
    a platform binary, console ROM, or a promise of a particular GPU API.
    One horizontal collider is emitted for each contiguous wall run.
    """
    args = _fields(arguments, {"tiles"})
    level = compile_level(args)
    rows, spawn, goal = _map(args["tiles"])
    rectangles: list[dict[str, int]] = []
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            if row[x] != "#":
                x += 1
                continue
            origin = x
            while x < len(row) and row[x] == "#":
                x += 1
            rectangles.append({
                "x": origin, "y": y, "width": x - origin, "height": 1,
            })
    covered = sum(item["width"] * item["height"] for item in rectangles)
    if covered != level["solid_count"]:
        raise GameplayError("compiled collider count disagrees with source map")
    return {
        "schema_version": "skeleton.gameplay.engine_neutral_scene.v1",
        "coordinate_system": "integer_grid_y_down",
        "tile_size": 1,
        "width": level["width"],
        "height": level["height"],
        "source_tile_digest": level["tile_digest"],
        "collider_rectangles": rectangles,
        "collider_count": len(rectangles),
        "solid_tiles_covered": covered,
        "entities": [
            {"id": "player", "kind": "controllable_actor",
             "position": _point(spawn), "velocity": {"x": 0, "y": 0}},
            {"id": "goal", "kind": "goal_trigger",
             "position": _point(goal)},
        ],
        "goal_reachable": level["goal_reachable"],
        "external_artwork_included": False,
        "native_executable_created": False,
        "training_examples_added": 0,
    }


def generate_level(arguments: dict[str, Any]) -> dict[str, Any]:
    """Create an original solvable maze tilemap from a stable seed.

    No RNG global state, files, external assets or learned weights. The
    carved corridor guarantees a walkable path between spawn and goal.
    """
    args = _fields(arguments, {"seed", "width", "height", "wall_percent"})
    seed = _integer(args["seed"], 0, 2**31 - 1)
    width = _integer(args["width"], MIN_DIM, MAX_DIM)
    height = _integer(args["height"], MIN_DIM, MAX_DIM)
    density = _integer(args["wall_percent"], 0, 70)
    grid = [["#" for _ in range(width)] for _ in range(height)]
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            # SHA256-derived cell decisions prevent host-specific RNG drift.
            candidate = hashlib.sha256(
                f"skeleton-game-v1:{seed}:{x}:{y}".encode("ascii")
            ).digest()
            grid[y][x] = "#" if int.from_bytes(candidate[:4], "big") % 100 < density else "."
    start = (1, 1)
    finish = (width - 2, height - 2)
    # Carve a deterministic corridor. Mark spawn/goal after carving.
    for x in range(start[0], finish[0] + 1):
        grid[start[1]][x] = "."
    for y in range(start[1], finish[1] + 1):
        grid[y][finish[0]] = "."
    grid[start[1]][start[0]] = "S"
    grid[finish[1]][finish[0]] = "G"
    tiles = ["".join(line) for line in grid]
    compiled = compile_level({"tiles": tiles})
    if not compiled["goal_reachable"]:
        raise GameplayError("deterministic maze generation broke its corridor")
    return {
        "schema_version": "skeleton.gameplay.generated_level.v1",
        "seed": seed,
        "wall_percent_requested": density,
        "tiles": tiles,
        "tile_digest": compiled["tile_digest"],
        "goal_reachable": True,
        "shortest_goal_steps": compiled["shortest_goal_steps"],
        "training_examples_added": 0,
        "external_assets_used": False,
    }


def _avatar(value: Any, rows: tuple[str, ...]) -> dict[str, int]:
    actor = _fields(value, {"x", "y", "vx", "vy"})
    x = _integer(actor["x"], 0, len(rows[0]) - 1)
    y = _integer(actor["y"], 0, len(rows) - 1)
    vx = _integer(actor["vx"], -MAX_SPEED, MAX_SPEED)
    vy = _integer(actor["vy"], -MAX_SPEED, MAX_SPEED)
    if not _traversable(rows, x, y):
        raise GameplayError("avatar occupies a wall or leaves the map")
    return {"x": x, "y": y, "vx": vx, "vy": vy}


def _buttons(value: Any) -> dict[str, bool]:
    data = _fields(value, {"left", "right", "jump"})
    if any(type(item) is not bool for item in data.values()):
        raise GameplayError("controller inputs must be booleans")
    return data


def _advance(
    rows: tuple[str, ...], current: dict[str, int], control: dict[str, bool],
    goal: tuple[int, int],
) -> dict[str, Any]:
    x, y, old_vy = current["x"], current["y"], current["vy"]
    grounded_before = not _traversable(rows, x, y + 1)
    vx = int(control["right"]) - int(control["left"])
    vy = -3 if control["jump"] and grounded_before else min(MAX_SPEED, old_vy + 1)
    if not _traversable(rows, x + vx, y):
        vx = 0
    x += vx
    # A goal must register whenever the actor ENTERS it, even if a later
    # gravity substep moves it out of the goal before the frame boundary.
    touched_goal = (x, y) == goal
    moved_y = 0
    for _ in range(abs(vy)):
        ny = y + (1 if vy > 0 else -1)
        if not _traversable(rows, x, ny):
            vy = 0
            break
        y = ny
        touched_goal = touched_goal or (x, y) == goal
        moved_y += 1
    grounded_after = not _traversable(rows, x, y + 1)
    # Velocity becomes zero when a wall stopped vertical movement.
    return {
        "avatar": {"x": x, "y": y, "vx": vx, "vy": vy},
        "grounded": grounded_after,
        "goal_reached": touched_goal,
        "vertical_cells_traversed": moved_y,
    }


def platformer_step(arguments: dict[str, Any]) -> dict[str, Any]:
    """One deterministic integer-tick 1x1 actor step; no tunneling."""
    args = _fields(arguments, {"tiles", "avatar", "control"})
    rows, _, goal = _map(args["tiles"])
    state = _avatar(args["avatar"], rows)
    buttons = _buttons(args["control"])
    return _advance(rows, state, buttons, goal)


def platformer_replay(arguments: dict[str, Any]) -> dict[str, Any]:
    """Replay up to 64 frames and return a hashed inspectable state trace."""
    args = _fields(arguments, {"tiles", "avatar", "controls"})
    rows, _, goal = _map(args["tiles"])
    avatar = _avatar(args["avatar"], rows)
    controls = args["controls"]
    if not isinstance(controls, list) or not 1 <= len(controls) <= MAX_FRAMES:
        raise GameplayError("replay must have between 1 and 64 controller frames")
    trace: list[dict[str, Any]] = []
    won_at: int | None = None
    for i, action in enumerate(controls):
        buttons = _buttons(action)
        state = _advance(rows, avatar, buttons, goal)
        avatar = state["avatar"]
        trace.append({"frame": i + 1, **state})
        if state["goal_reached"] and won_at is None:
            won_at = i + 1
    return {
        "schema_version": "skeleton.gameplay.replay.v1",
        "frames_simulated": len(trace),
        "final_avatar": avatar,
        "goal_first_reached_frame": won_at,
        "trace": trace,
        "trace_sha256": _digest(trace),
        "trained_model_used": False,
        "training_examples_added": 0,
    }


def tile_line_of_sight(arguments: dict[str, Any]) -> dict[str, Any]:
    """Integer Bresenham cast; walls include endpoints, no diagonal corner passthrough."""
    args = _fields(arguments, {"tiles", "start", "goal"})
    rows, _, _ = _map(args["tiles"])
    def cell(value: Any) -> tuple[int, int]:
        item = _fields(value, {"x", "y"})
        x = _integer(item["x"], 0, len(rows[0]) - 1)
        y = _integer(item["y"], 0, len(rows) - 1)
        return x, y
    x0, y0 = cell(args["start"])
    x1, y1 = cell(args["goal"])
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx - dy
    examined: list[dict[str, int]] = []
    while True:
        examined.append({"x": x0, "y": y0})
        if not _traversable(rows, x0, y0):
            return {"visible": False, "blocked_at": _point((x0, y0)),
                    "cells_examined": examined}
        if x0 == x1 and y0 == y1:
            return {"visible": True, "blocked_at": None, "cells_examined": examined}
        doubled = error * 2
        next_x, next_y = x0, y0
        if doubled > -dy:
            error -= dy
            next_x += sx
        if doubled < dx:
            error += dx
            next_y += sy
        # Closed corners: cannot see through a pinhole between two walls.
        if next_x != x0 and next_y != y0:
            if not _traversable(rows, next_x, y0) and not _traversable(rows, x0, next_y):
                return {
                    "visible": False,
                    "blocked_at": _point((next_x, next_y)),
                    "cells_examined": examined,
                }
        x0, y0 = next_x, next_y


GAMEPLAY_OPERATIONS = {
    "game.level_generate": generate_level,
    "game.level_compile": compile_level,
    "game.scene_compile": compile_native_scene,
    "game.platformer_step": platformer_step,
    "game.platformer_replay": platformer_replay,
    "game.tile_line_of_sight": tile_line_of_sight,
}


__all__ = ["GameplayError", "GAMEPLAY_OPERATIONS", "compile_level",
           "compile_native_scene",
           "generate_level", "platformer_step", "platformer_replay",
           "tile_line_of_sight"]
