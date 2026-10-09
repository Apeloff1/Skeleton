"""Homebrew-only deterministic map editor, offline procedural assistant and audit.

Not a language-model-based editor. All operators are typed, reproducible
and bounded. No imported game image, arbitrary script, executable binary,
ROM, SDK, network, remote asset or training sample can enter this plane.
The final project carries only ORIGINAL asset attestations and must pass
the independent original-homebrew capsule verifier before any export.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import hashlib
import json
from typing import Any, Mapping

from .gameplay_capabilities import GameplayError, compile_level, compile_native_scene
from .game_playability import check_game_playability
from .game_project_capsule import make_game_capsule, verify_game_capsule, MAX_EDITS
from .game_platform_catalog import TARGETS, plan_game_targets
from .game_rights import GameRightsError, admit_homebrew_project

MAX_COMMANDS = 256
MAX_BATCH = 32
MAX_BRUSH_RADIUS = 10
MAX_STAMP_DIM = 16
MAX_GENERATED_VARIANTS = 8
MAX_HISTORY = 128
TILES = frozenset("#.SG")


class HomebrewEditorError(ValueError):
    """Invalid mutation, conflict, exceeded bound or non-homebrew input."""


def _canonical(data: Any) -> bytes:
    try:
        return json.dumps(data, sort_keys=True, ensure_ascii=True,
                          allow_nan=False, separators=(",", ":")).encode("ascii")
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise HomebrewEditorError("unserializable game editor command") from exc


def _digest(data: Any) -> str:
    return hashlib.sha256(_canonical(data)).hexdigest()


def _integer(value: Any, lo: int, hi: int) -> int:
    if type(value) is not int or not lo <= value <= hi:
        raise HomebrewEditorError(f"integer must be within {lo}..{hi}")
    return value


def _only(cmd: Any, keys: set[str]) -> dict[str, Any]:
    if not isinstance(cmd, dict) or set(cmd) != keys:
        raise HomebrewEditorError("command has unexpected or missing fields")
    return cmd


def _tile(value: Any) -> str:
    if type(value) is not str or value not in ("#", "."):
        raise HomebrewEditorError("direct brushes may only paint original wall/floor tiles")
    return value


def _xy(grid: list[list[str]], x: Any, y: Any) -> tuple[int, int]:
    return (_integer(x, 0, len(grid[0]) - 1),
            _integer(y, 0, len(grid) - 1))


def _paint(grid: list[list[str]], x: int, y: int, tile: str) -> None:
    if grid[y][x] in ("S", "G"):
        raise HomebrewEditorError("spawn/goal cannot be erased by a terrain brush")
    grid[y][x] = tile


def _line(x0: int, y0: int, x1: int, y1: int):
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    error = dx - dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            return
        twice = error * 2
        if twice > -dy:
            error -= dy
            x0 += sx
        if twice < dx:
            error += dx
            y0 += sy


def _make_change(grid: list[list[str]], cmd: dict[str, Any]) -> None:
    if not isinstance(cmd, dict) or not isinstance(cmd.get("op"), str):
        raise HomebrewEditorError("editor commands must be objects with explicit op")
    op = cmd["op"]
    h, w = len(grid), len(grid[0])
    if op == "paint":
        _only(cmd, {"op", "x", "y", "tile"})
        x, y = _xy(grid, cmd["x"], cmd["y"])
        _paint(grid, x, y, _tile(cmd["tile"]))
    elif op == "brush":
        _only(cmd, {"op", "x", "y", "radius", "shape", "tile"})
        x, y = _xy(grid, cmd["x"], cmd["y"])
        radius = _integer(cmd["radius"], 0, MAX_BRUSH_RADIUS)
        if cmd["shape"] not in ("square", "diamond", "circle"):
            raise HomebrewEditorError("brush geometry unsupported")
        tile = _tile(cmd["tile"])
        for row in range(max(0, y - radius), min(h, y + radius + 1)):
            for col in range(max(0, x - radius), min(w, x + radius + 1)):
                dx, dy = abs(col - x), abs(row - y)
                inside = (
                    cmd["shape"] == "square"
                    or cmd["shape"] == "diamond" and dx + dy <= radius
                    or cmd["shape"] == "circle" and dx * dx + dy * dy <= radius * radius
                )
                if inside and grid[row][col] not in ("S", "G"):
                    _paint(grid, col, row, tile)
    elif op == "line":
        _only(cmd, {"op", "x0", "y0", "x1", "y1", "tile"})
        x0, y0 = _xy(grid, cmd["x0"], cmd["y0"])
        x1, y1 = _xy(grid, cmd["x1"], cmd["y1"])
        tile = _tile(cmd["tile"])
        for x, y in _line(x0, y0, x1, y1):
            if grid[y][x] not in ("S", "G"):
                _paint(grid, x, y, tile)
    elif op == "rectangle":
        _only(cmd, {"op", "x0", "y0", "x1", "y1", "tile", "filled"})
        x0, y0 = _xy(grid, cmd["x0"], cmd["y0"])
        x1, y1 = _xy(grid, cmd["x1"], cmd["y1"])
        if type(cmd["filled"]) is not bool:
            raise HomebrewEditorError("rectangle filled must be boolean")
        tile = _tile(cmd["tile"])
        xa, xb = sorted((x0, x1))
        ya, yb = sorted((y0, y1))
        for y in range(ya, yb + 1):
            for x in range(xa, xb + 1):
                if cmd["filled"] or x in (xa, xb) or y in (ya, yb):
                    if grid[y][x] not in ("S", "G"):
                        _paint(grid, x, y, tile)
    elif op == "flood":
        _only(cmd, {"op", "x", "y", "tile"})
        x, y = _xy(grid, cmd["x"], cmd["y"])
        tile = _tile(cmd["tile"])
        old = grid[y][x]
        if old in ("S", "G"):
            raise HomebrewEditorError("cannot flood player or goal")
        if old != tile:
            queue = deque([(x, y)])
            grid[y][x] = tile
            while queue:
                px, py = queue.popleft()
                for nx, ny in ((px + 1, py), (px - 1, py),
                               (px, py + 1), (px, py - 1)):
                    if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == old:
                        grid[ny][nx] = tile
                        queue.append((nx, ny))
    elif op == "stamp":
        _only(cmd, {"op", "x", "y", "pattern"})
        x, y = _xy(grid, cmd["x"], cmd["y"])
        rows = cmd["pattern"]
        if (not isinstance(rows, list) or not 1 <= len(rows) <= MAX_STAMP_DIM
                or any(not isinstance(row, str) for row in rows)
                or not 1 <= len(rows[0]) <= MAX_STAMP_DIM
                or any(len(row) != len(rows[0]) or set(row) - set("#.?")
                       for row in rows)
                or x + len(rows[0]) > w or y + len(rows) > h):
            raise HomebrewEditorError("stamp must be bounded #/. /? pattern inside map")
        for dy, line in enumerate(rows):
            for dx, tile in enumerate(line):
                if tile != "?":
                    _paint(grid, x + dx, y + dy, tile)
    elif op == "move_marker":
        _only(cmd, {"op", "marker", "x", "y"})
        marker = cmd["marker"]
        if marker not in ("S", "G"):
            raise HomebrewEditorError("only spawn and goal markers can move")
        x, y = _xy(grid, cmd["x"], cmd["y"])
        if grid[y][x] not in (".", marker):
            raise HomebrewEditorError("marker destination must be open floor")
        prev = [(i, j) for j, row in enumerate(grid)
                for i, current in enumerate(row) if current == marker]
        if len(prev) != 1:
            raise HomebrewEditorError("editor lost unique marker")
        px, py = prev[0]
        grid[py][px] = "."
        grid[y][x] = marker
    elif op == "transform":
        _only(cmd, {"op", "mode"})
        mode = cmd["mode"]
        if mode == "flip_horizontal":
            for row in grid:
                row.reverse()
        elif mode == "flip_vertical":
            grid.reverse()
        elif mode == "rotate_180":
            grid.reverse()
            for row in grid:
                row.reverse()
        else:
            raise HomebrewEditorError("unsupported geometric transform")
    elif op == "noise":
        _only(cmd, {"op", "seed", "wall_percent", "x0", "y0", "x1", "y1"})
        seed = _integer(cmd["seed"], 0, 2**31 - 1)
        density = _integer(cmd["wall_percent"], 0, 100)
        x0, y0 = _xy(grid, cmd["x0"], cmd["y0"])
        x1, y1 = _xy(grid, cmd["x1"], cmd["y1"])
        for y in range(min(y0, y1), max(y0, y1) + 1):
            for x in range(min(x0, x1), max(x0, x1) + 1):
                if grid[y][x] in ("S", "G"):
                    continue
                sample = hashlib.sha256(
                    f"homebrew-noise-v1:{seed}:{x}:{y}".encode("ascii")
                ).digest()
                _paint(grid, x, y, "#" if int.from_bytes(sample[:4], "big") % 100 < density else ".")
    elif op == "smooth":
        _only(cmd, {"op", "iterations", "threshold"})
        times = _integer(cmd["iterations"], 1, 4)
        threshold = _integer(cmd["threshold"], 3, 8)
        for _ in range(times):
            previous = [row[:] for row in grid]
            for y in range(1, h - 1):
                for x in range(1, w - 1):
                    if previous[y][x] in ("S", "G"):
                        continue
                    walls = sum(
                        previous[y + dy][x + dx] == "#"
                        for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                        if dx or dy
                    )
                    grid[y][x] = "#" if walls >= threshold else "."
    elif op == "carve_route":
        _only(cmd, {"op", "order"})
        if cmd["order"] not in ("horizontal_first", "vertical_first"):
            raise HomebrewEditorError("route order unsupported")
        source = [(x, y) for y, row in enumerate(grid)
                  for x, tile in enumerate(row) if tile == "S"]
        goal = [(x, y) for y, row in enumerate(grid)
                for x, tile in enumerate(row) if tile == "G"]
        if len(source) != 1 or len(goal) != 1:
            raise HomebrewEditorError("route requires one spawn and goal")
        sx, sy = source[0]
        gx, gy = goal[0]
        mid = (gx, sy) if cmd["order"] == "horizontal_first" else (sx, gy)
        for pair in ((sx, sy, *mid), (*mid, gx, gy)):
            for x, y in _line(*pair):
                if grid[y][x] not in ("S", "G"):
                    _paint(grid, x, y, ".")
    else:
        raise HomebrewEditorError("unknown or unsupported homebrew editor operator")


def _as_rows(grid: list[list[str]]) -> list[str]:
    return ["".join(row) for row in grid]


def analyze_homebrew_level(tiles: list[str], *, target_ids: list[str] | None = None,
                           search_frames: int = 96) -> dict[str, Any]:
    """Rich, deterministic static analysis + actual controller feasibility."""
    try:
        level = compile_level({"tiles": tiles})
        scene = compile_native_scene({"tiles": tiles})
        playable = check_game_playability({
            "tiles": tiles, "max_frames": search_frames,
        })
    except (GameplayError, TypeError) as exc:
        raise HomebrewEditorError("cannot analyze invalid homebrew world") from exc
    solid = level["solid_count"]
    w, h = level["width"], level["height"]
    dead_ends = 0
    floor_sides = 0
    for y, row in enumerate(tiles):
        for x, ch in enumerate(row):
            if ch == "#":
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h and tiles[ny][nx] != "#":
                        floor_sides += 1
            else:
                neighbors = sum(
                    0 <= nx < w and 0 <= ny < h and tiles[ny][nx] != "#"
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                )
                if neighbors <= 1:
                    dead_ends += 1
    suggested: list[str] = []
    if not level["goal_reachable"]:
        suggested.append("carve_route")
    if playable["status"] != "playable":
        suggested.extend(("move_marker", "carve_route", "lower_obstacle_density"))
    if solid * 100 > w * h * 65:
        suggested.append("reduce_wall_density")
    if dead_ends > 4:
        suggested.append("reduce_dead_ends")
    if target_ids is None:
        target_ids = ["chip8-vip", "windows-11"]
    plan = plan_game_targets(
        target_ids=target_ids, required_features=["tile2d", "input"],
    )
    targets: list[dict[str, Any]] = []
    for target in plan["targets"]:
        tid = target["id"]
        targets.append({
            "target": tid,
            "exporter_implemented": target["native_export_implemented"],
            "design_features_supported": target["design_feasibility_estimated"],
            "specific_map_dimensions_fit": (
                w <= 8 and h <= 8 if tid == "chip8-vip" else None
            ),
            "release_approved": False,
            "rights_independently_verified": False,
        })
    return {
        "schema_version": "skeleton.game.homebrew_analysis.v1",
        "tile_sha256": level["tile_digest"],
        "width": w, "height": h,
        "wall_tiles": solid,
        "wall_density_percent": round(100 * solid / (w * h), 2),
        "reachable_tiles": level["reachable_from_spawn"],
        "walkable_tiles": level["walkable_count"],
        "shortest_grid_path": level["shortest_goal_steps"],
        "goal_grid_reachable": level["goal_reachable"],
        "controller_status": playable["status"],
        "winning_input_frames": playable["controller_frames"],
        "winning_inputs_sha256": playable["controls_sha256"],
        "search_states": playable["states_explored"],
        "collider_rectangles": scene["collider_count"],
        "dead_ends": dead_ends,
        "wall_to_floor_edges": floor_sides,
        "horizontal_symmetry": all(row == row[::-1] for row in tiles),
        "vertical_symmetry": tiles == tiles[::-1],
        "suggested_editor_tools": sorted(set(suggested)),
        "target_options": targets,
        "training_examples_added": 0,
        "independently_verified_asset_rights": False,
    }


EDITOR_TOOLS = (
    "paint", "brush", "line", "rectangle", "flood", "stamp",
    "move_marker", "transform", "noise", "smooth", "carve_route",
)
OPERATOR_GUIDE = {
    "paint": {"fields": ("x", "y", "tile"), "domain": "single terrain cell"},
    "brush": {"fields": ("x", "y", "radius", "shape", "tile"), "shapes": ("square", "diamond", "circle")},
    "line": {"fields": ("x0", "y0", "x1", "y1", "tile"), "path": "integer Bresenham"},
    "rectangle": {"fields": ("x0", "y0", "x1", "y1", "tile", "filled"), "filled": "bool"},
    "flood": {"fields": ("x", "y", "tile"), "adjacency": 4},
    "stamp": {"fields": ("x", "y", "pattern"), "transparent_symbol": "?"},
    "move_marker": {"fields": ("marker", "x", "y"), "marker": ("S", "G")},
    "transform": {"fields": ("mode",), "mode": ("flip_horizontal", "flip_vertical", "rotate_180")},
    "noise": {"fields": ("seed", "wall_percent", "x0", "y0", "x1", "y1"), "seeded": True},
    "smooth": {"fields": ("iterations", "threshold"), "neighborhood": 8},
    "carve_route": {"fields": ("order",), "order": ("horizontal_first", "vertical_first")},
}


class HomebrewEditor:
    """Atomic, replayable, undoable original homebrew editor session."""

    def __init__(self, capsule: dict[str, Any]) -> None:
        try:
            verify_game_capsule(capsule)
            admit_homebrew_project(
                capsule["rights_manifest"], action=capsule["action"],
                jurisdiction=capsule["jurisdiction"],
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise HomebrewEditorError("editor only opens verified original homebrew capsules") from exc
        self.source = deepcopy(capsule)
        self.base = list(capsule["source_tilemap"])
        self.tiles = list(capsule["tilemap"])
        self.history = [self.tiles[:]]
        self.cursor = 0
        self.events: list[dict[str, Any]] = []
        self.audit_sha256 = "0" * 64
        self.command_count = 0

    @property
    def tile_sha256(self) -> str:
        return compile_level({"tiles": self.tiles})["tile_digest"]

    def apply(
        self, commands: list[dict[str, Any]], *,
        expected_tile_sha256: str,
        require_grid_route: bool = True,
        require_controller_win: bool = False,
    ) -> dict[str, Any]:
        if (
            not isinstance(commands, list)
            or not 1 <= len(commands) <= MAX_BATCH
            or self.command_count + len(commands) > MAX_COMMANDS
            or type(expected_tile_sha256) is not str
            or expected_tile_sha256 != self.tile_sha256
            or type(require_grid_route) is not bool
            or type(require_controller_win) is not bool
        ):
            raise HomebrewEditorError(
                "invalid command batch, budget or optimistic-lock tile hash"
            )
        updated = [list(row) for row in self.tiles]
        for cmd in commands:
            _make_change(updated, cmd)
        candidate = _as_rows(updated)
        try:
            level = compile_level({"tiles": candidate})
            if require_grid_route and not level["goal_reachable"]:
                raise HomebrewEditorError("edit would disconnect the goal")
            if require_controller_win:
                evidence = check_game_playability({
                    "tiles": candidate, "max_frames": 96,
                })
                if evidence["status"] != "playable":
                    raise HomebrewEditorError(
                        "edit failed actual controller-playability proof"
                    )
        except GameplayError as exc:
            raise HomebrewEditorError("edit produced invalid level geometry") from exc
        previous_sha = self.tile_sha256
        self.tiles = candidate
        self.history = self.history[:self.cursor + 1]
        if len(self.history) >= MAX_HISTORY:
            self.history.pop(0)
            self.cursor -= 1
        self.history.append(candidate[:])
        self.cursor += 1
        self.command_count += len(commands)
        audit = {
            "sequence": len(self.events) + 1,
            "parent_audit_sha256": self.audit_sha256,
            "old_tile_sha256": previous_sha,
            "new_tile_sha256": level["tile_digest"],
            "commands": deepcopy(commands),
            "constraint_grid_reachable": require_grid_route,
            "constraint_controller_winnable": require_controller_win,
        }
        self.audit_sha256 = _digest(audit)
        self.events.append({**audit, "event_sha256": self.audit_sha256})
        return {
            "new_tile_sha256": self.tile_sha256,
            "batch_operations": len(commands),
            "commands_spent": self.command_count,
            "undo_available": self.cursor > 0,
            "redo_available": False,
            "audit_sha256": self.audit_sha256,
            "goal_grid_reachable": level["goal_reachable"],
            "training_examples_added": 0,
        }

    def undo(self) -> list[str]:
        if self.cursor == 0:
            raise HomebrewEditorError("no additional edit to undo")
        self.cursor -= 1
        self.tiles = self.history[self.cursor][:]
        return self.tiles[:]

    def redo(self) -> list[str]:
        if self.cursor >= len(self.history) - 1:
            raise HomebrewEditorError("no additional edit to redo")
        self.cursor += 1
        self.tiles = self.history[self.cursor][:]
        return self.tiles[:]

    def analyze(self, *, target_ids: list[str] | None = None) -> dict[str, Any]:
        return analyze_homebrew_level(self.tiles, target_ids=target_ids)

    def variants(
        self, *, seeds: list[int], wall_percent: int,
        require_controller_win: bool = False,
    ) -> list[dict[str, Any]]:
        if (not isinstance(seeds, list)
                or not 1 <= len(seeds) <= MAX_GENERATED_VARIANTS
                or len(set(str(seed) for seed in seeds)) != len(seeds)
                or type(require_controller_win) is not bool):
            raise HomebrewEditorError("original procedural variant batch exceeds budget")
        density = _integer(wall_percent, 0, 80)
        variants: list[dict[str, Any]] = []
        for seed in seeds:
            seed = _integer(seed, 0, 2**31 - 1)
            draft = [list(row) for row in self.tiles]
            for y in range(1, len(draft) - 1):
                for x in range(1, len(draft[0]) - 1):
                    if draft[y][x] in ("S", "G"):
                        continue
                    salt = hashlib.sha256(
                        f"homebrew-noise-v1:{seed}:{x}:{y}".encode("ascii")
                    ).digest()
                    draft[y][x] = "#" if int.from_bytes(salt[:4], "big") % 100 < density else "."
            candidate = _as_rows(draft)
            analysis = analyze_homebrew_level(candidate, target_ids=["chip8-vip"])
            if require_controller_win and analysis["controller_status"] != "playable":
                continue
            variants.append({
                "seed": seed,
                "tiles": candidate,
                "analysis": analysis,
                "source_tiles_original": True,
                "training_examples_added": 0,
            })
        # The operator chooses a candidate. We NEVER mutate state while
        # searching or invent rights/quality-of-game scores.
        variants.sort(key=lambda entry: (
            entry["analysis"]["controller_status"] != "playable",
            entry["analysis"]["dead_ends"],
            entry["seed"],
        ))
        return variants

    def export_capsule(self) -> dict[str, Any]:
        changes = [
            {"x": x, "y": y, "tile": self.tiles[y][x]}
            for y, row in enumerate(self.base)
            for x, original in enumerate(row)
            if original != self.tiles[y][x]
        ]
        if len(changes) > MAX_EDITS:
            raise HomebrewEditorError("final project exceeds 1024 edited-cell budget")
        # Existing capsule's base provenance is an input to a NEW capsule,
        # never a new authorization or imported copyrighted source.
        try:
            target_ids = [
                row["id"] for row in self.source["target_plan"]["targets"]
            ]
            requested = self.source["target_plan"]["targets"][0]["requested_features"]
            product = make_game_capsule(
                source_tiles=self.base,
                rights_manifest=deepcopy(self.source["rights_manifest"]),
                target_ids=target_ids,
                required_features=requested,
                action=self.source["action"],
                jurisdiction=self.source["jurisdiction"],
                edits=changes,
            )
            verify_game_capsule(product)
        except (ValueError, KeyError, TypeError) as exc:
            raise HomebrewEditorError("edited homebrew project failed export admission") from exc
        return product

    def capabilities(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.game.homebrew_editor_tools.v1",
            "homebrew_only": True,
            "original_assets_only": True,
            "tool_count": len(OPERATOR_GUIDE),
            "tools": deepcopy(OPERATOR_GUIDE),
            "max_commands": MAX_COMMANDS,
            "max_batch": MAX_BATCH,
            "max_edited_cells": MAX_EDITS,
            "max_canvas_side": 32,
            "undo_redo": True,
            "deterministic_multi_variant_search": True,
            "real_controller_playability_analysis": True,
            "source_rights_authorization_independently_verified": False,
            "third_party_game_import_allowed": False,
            "actual_hardware_release_complete": False,
            "model_training_examples_added": 0,
        }


__all__ = [
    "HomebrewEditorError", "HomebrewEditor", "analyze_homebrew_level",
    "EDITOR_TOOLS", "OPERATOR_GUIDE",
]
