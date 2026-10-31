"""Original sea, mountain, cave, elevation, adventure, homebrew, tabletop, and dungeon maps.

Each map is a deterministic variant. Sea charts separate deep water from the
shore. Mountain maps keep a peak above a valley. Cave floors connect to one
entrance. Elevation maps store one height per cell. Adventure maps link
original screens across seams, and a large height change is a stair.

These are not commercial charts and they do not reproduce another game's
world. Holdout serials are never training maps. A lower byte loss is not
gameplay quality, and this pass does not promote a serving checkpoint.
"""
from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import torch

from skeleton.ai.runtime.inference.game_adaptive_ratchet import (
    ADAMW_BETAS,
    ADAMW_EPS,
    ADAMW_WEIGHT_DECAY,
    GRAD_CLIP,
    AdaptiveRatchet,
    ByteRNN,
    _append_ledger,
    _batch_loss,
    _fresh_optimizer,
    _pin,
    _scores,
    network_digest,
)
from skeleton.ai.runtime.inference.game_coherent_english import (
    MILLION_WORD_DIGEST,
    budget_forecast,
    training_stop,
)
from skeleton.ai.runtime.inference.game_corpus_stream import (
    DENYLIST,
    HOLDOUT_SERIAL,
    SLOTS,
    banned_windows,
    leaks,
    track_holdouts,
    training_serial,
)
from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM

BILLION_MAPS = 1_000_000_000
SCHEMA = "skeleton.game_map_variants.v1"
FAMILIES: tuple[str, ...] = (
    "sea_map",
    "mountain_map",
    "cave_map",
    "elevation_map",
    "adventure_map",
    "homebrew_map",
    "tabletop_map",
    "dungeon_map",
)
FOLLOWUP_FAMILIES: tuple[str, ...] = ("homebrew_map", "tabletop_map", "dungeon_map")
VARIANTS: dict[str, tuple[str, ...]] = {
    "sea_map": ("bay", "atoll", "channel", "archipelago", "harbor"),
    "mountain_map": ("ridge", "pass", "peak", "saddle", "cliff"),
    "cave_map": ("tunnel", "chamber", "shaft", "fork", "shore"),
    "elevation_map": ("ramp", "hill", "valley", "plateau", "terrace"),
    "adventure_map": ("coast-link", "ridge-link", "cave-link", "island-link", "pass-link"),
    "homebrew_map": ("region", "route", "camp", "ruin", "ford"),
    "tabletop_map": ("skirmish", "ambush", "bridge", "courtyard", "shore"),
    "dungeon_map": ("corridor", "vault", "loop", "branch", "cellar"),
}
TABLETOP_TILES = {".", "#", "c", "d"}
HOMEBREW_TILES = {"#", ".", "~", "H", "K"}
WALK_HOME = {".", "~", "H", "K"}
WALK_TABLE = {".", "c", "d"}
ROOM_NAMES = ("entry", "hall", "cache", "stair", "well", "loft")
SIZES: tuple[tuple[int, int], ...] = ((8, 8), (12, 8), (8, 12), (16, 8))
SEA_ELEV = {"~": 0, "-": 1, "#": 2, "^": 3}
MOUNTAIN_ELEV = {"v": 0, ".": 1, "/": 2, "^": 3}
ADVENTURE_ELEV = {
    "coast-link": (1, 0, 2, 3),
    "ridge-link": (2, 5, 2, 5),
    "cave-link": (2, 2, 0, 4),
    "island-link": (1, 0, 0, 1),
    "pass-link": (3, 4, 1, 2),
}
OPPOSITE = {"east": "west", "west": "east", "north": "south", "south": "north"}
# Names from commercial adventure games. Original maps must not contain them.
RESERVED_NAMES = (
    "zelda",
    "hyrule",
    "ganon",
    "triforce",
    "kakariko",
    "gerudo",
    "kokiri",
    "midna",
    "ocarina",
    "majora",
    "calamity",
    "dungeons and dragons",
    "dungeons & dragons",
    "forgotten realms",
    "faerun",
    "waterdeep",
    "baldur",
    "underdark",
    "beholder",
    "mind flayer",
    "illithid",
    "tarrasque",
    "strahd",
    "ravenloft",
    "eberron",
    "dragonlance",
    "greyhawk",
    "mordenkainen",
    "vecna",
    "lolth",
    "neverwinter",
    "phandelver",
    "barovia",
)


def _size(serial: int) -> tuple[int, int]:
    return SIZES[serial % len(SIZES)]


def _variant(family: str, serial: int) -> str:
    options = VARIANTS[family]
    return options[(serial // len(SIZES)) % len(options)]


def _blank(width: int, height: int, fill: str) -> list[list[str]]:
    return [[fill for _ in range(width)] for _ in range(height)]


def _sea_grid(width: int, height: int, serial: int, variant: str) -> list[list[str]]:
    grid = _blank(width, height, "~")
    if variant == "bay":
        coast = 2 + (serial % max(1, height - 4))
        for y in range(coast, height):
            for x in range(width):
                grid[y][x] = "#"
        mouth = width // 2
        for y in range(coast, min(height, coast + 2)):
            for x in range(max(0, mouth - 1), min(width, mouth + 2)):
                grid[y][x] = "-"
        grid[min(height - 1, coast + 1)][mouth] = "^"
    elif variant == "atoll":
        for y in range(height):
            for x in range(width):
                edge = x == 0 or y == 0 or x == width - 1 or y == height - 1
                grid[y][x] = "#" if edge else "~"
        grid[height // 2][0] = "-"
        grid[0][width // 2] = "^"
    elif variant == "channel":
        top = height // 3
        bottom = max(top + 1, 2 * height // 3)
        for y in range(height):
            tile = "-" if top <= y < bottom else "#"
            for x in range(width):
                grid[y][x] = tile
        grid[top][width // 2] = "^"
    elif variant == "archipelago":
        for index in range(3):
            cx = (serial + index * 3) % width
            cy = (serial // 3 + index * 2) % height
            grid[cy][cx] = "#"
            if cx + 1 < width:
                grid[cy][cx + 1] = "-"
        grid[0][0] = "^"
    else:
        shore = max(2, height // 2)
        for y in range(shore, height):
            for x in range(width):
                grid[y][x] = "#"
        dock = width // 3
        for y in range(shore - 2, shore):
            grid[y][dock] = "#"
        grid[shore - 1][min(width - 1, dock + 1)] = "^"
        for x in range(width):
            if grid[shore - 1][x] == "~":
                grid[shore - 1][x] = "-"
    return grid


def _mountain_grid(width: int, height: int, serial: int, variant: str) -> list[list[str]]:
    grid = _blank(width, height, ".")
    if variant == "ridge":
        row = 1 + (serial % max(1, height - 2))
        for x in range(width):
            grid[row][x] = "^"
            if row - 1 >= 0:
                grid[row - 1][x] = "/"
            if row + 1 < height:
                grid[row + 1][x] = "v" if x == width // 2 else "."
    elif variant == "pass":
        row = height // 2
        gap = width // 2
        for x in range(width):
            grid[row][x] = "." if x == gap else "^"
            if row + 1 < height:
                grid[row + 1][x] = "v"
            if row - 1 >= 0:
                grid[row - 1][x] = "/"
    elif variant == "peak":
        cx, cy = width // 2, height // 2
        for y in range(height):
            for x in range(width):
                distance = max(abs(x - cx), abs(y - cy))
                grid[y][x] = "^" if distance == 0 else "/" if distance == 1 else "." if distance == 2 else "v"
    elif variant == "saddle":
        for y in range(height):
            for x in range(width):
                if x == width // 2:
                    grid[y][x] = "v"
                elif x == 0 or x == width - 1:
                    grid[y][x] = "^"
                else:
                    grid[y][x] = "/"
    else:
        split = width // 2
        for y in range(height):
            for x in range(width):
                grid[y][x] = "v" if x < split else "^"
        grid[height // 2][split] = "."
        if split - 1 >= 0:
            grid[height // 2][split - 1] = "/"
    return grid


def _cave_grid(width: int, height: int, serial: int, variant: str) -> tuple[list[list[str]], tuple[int, int]]:
    grid = _blank(width, height, "#")
    if variant == "tunnel":
        y = height // 2
        for x in range(width):
            grid[y][x] = "."
        entrance = (0, y)
    elif variant == "shaft":
        x = width // 2
        for y in range(height):
            grid[y][x] = "."
        entrance = (x, 0)
    elif variant == "chamber":
        y = height // 2
        for x in range(width // 2 + 1):
            grid[y][x] = "."
        for yy in range(max(1, height // 4), min(height - 1, 3 * height // 4 + 1)):
            for xx in range(width // 2, width - 1):
                grid[yy][xx] = "."
        entrance = (0, y)
    elif variant == "fork":
        y = height // 2
        mid = width // 2
        for x in range(mid + 1):
            grid[y][x] = "."
        for yy in range(height):
            grid[yy][mid] = "."
        entrance = (0, y)
    else:
        y = height // 2
        for x in range(min(2, width)):
            grid[y][x] = "~"
        for x in range(min(2, width), width):
            grid[y][x] = "."
        entrance = (0, y)
    if serial % 2 and variant != "shaft":
        # A second original branch that still touches the main floor.
        grid[max(0, entrance[1] - 1)][min(width - 1, entrance[0] + 1)] = "."
    return grid, entrance


def _elevation_grid(width: int, height: int, variant: str) -> list[list[int]]:
    grid = [[0 for _ in range(width)] for _ in range(height)]
    cx, cy = (width - 1) / 2, (height - 1) / 2
    for y in range(height):
        for x in range(width):
            if variant == "ramp":
                grid[y][x] = min(9, x * 9 // max(1, width - 1))
            elif variant == "hill":
                distance = max(abs(x - cx), abs(y - cy))
                grid[y][x] = max(0, 9 - int(distance * 2))
            elif variant == "valley":
                distance = max(abs(x - cx), abs(y - cy))
                grid[y][x] = min(9, int(distance * 2))
            elif variant == "plateau":
                inside = width // 4 <= x < width - width // 4 and height // 4 <= y < height - max(1, height // 4)
                grid[y][x] = 7 if inside else 2
            else:
                grid[y][x] = min(9, y * 9 // max(1, height - 1))
    return grid


def _paint(grid: list[list[str]]) -> str:
    return "\n".join("".join(row) for row in grid)


def _digits(grid: list[list[int]]) -> str:
    return "\n".join(" ".join(str(cell) for cell in row) for row in grid)


def _adventure(serial: int, variant: str) -> str:
    places = SLOTS["place"]
    names = [places[(serial + index) % len(places)] for index in range(4)]
    letters = ("A", "B", "C", "D")
    heights = ADVENTURE_ELEV[variant]
    elev = dict(zip(letters, heights))
    links = (
        ("A", "east", "B"),
        ("B", "west", "A"),
        ("A", "south", "C"),
        ("C", "north", "A"),
        ("B", "south", "D"),
        ("D", "north", "B"),
        ("C", "east", "D"),
        ("D", "west", "C"),
    )
    stairs = [f"{left} {direction}" for left, direction, right in links if abs(elev[left] - elev[right]) > 1]
    screen_line = " ".join(
        f"Screen {letter} is {name} at elevation {elev[letter]}."
        for letter, name in zip(letters, names)
    )
    link_line = "Links " + ", ".join(f"{left} {direction} {right}" for left, direction, right in links) + "."
    stair_line = "Stairs " + ", ".join(stairs) + "." if stairs else "Stairs none."
    return "\n".join(
        (
            f"Adventure map variant {variant} screens 2x2 pass {serial}.",
            "AB",
            "CD",
            screen_line,
            link_line,
            stair_line,
            "The seam returns the same way it was crossed. A height change above one is a stair.",
        )
    )


def _stamp(grid: list[list[str]], x: int, y: int, tile: str) -> None:
    grid[y][x] = tile


def _homebrew_grid(width: int, height: int, variant: str) -> list[list[str]]:
    grid = _blank(width, height, "#")
    mid_y = height // 2
    mid_x = width // 2
    if variant == "route":
        for x in range(width):
            grid[mid_y][x] = "."
        _stamp(grid, 0, mid_y, "H")
        _stamp(grid, width - 1, mid_y, "K")
    elif variant == "camp":
        _stamp(grid, mid_x, mid_y, "H")
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1)):
            x, y = mid_x + dx, mid_y + dy
            if 0 <= x < width and 0 <= y < height and grid[y][x] == "#":
                grid[y][x] = "."
        _stamp(grid, min(width - 1, mid_x + 1), min(height - 1, mid_y + 1), "K")
    elif variant == "ruin":
        for y in range(1, max(2, height - 1)):
            for x in range(1, max(2, width - 1)):
                grid[y][x] = "."
        _stamp(grid, 0, mid_y, "H")
        if width > 1:
            grid[mid_y][1] = "."
        _stamp(grid, mid_x, mid_y, "K")
    elif variant == "ford":
        for x in range(width):
            grid[mid_y][x] = "~"
        _stamp(grid, 0, mid_y, "H")
        _stamp(grid, width - 1, mid_y, "K")
        grid[mid_y][mid_x] = "."
    else:
        for x in range(width):
            grid[mid_y][x] = "."
        _stamp(grid, 0, mid_y, "H")
        _stamp(grid, mid_x, mid_y, "K")
        if mid_y > 0:
            grid[mid_y - 1][mid_x] = "."
    return grid


def _tabletop_grid(width: int, height: int, variant: str) -> list[list[str]]:
    grid = _blank(width, height, ".")
    mid_y = height // 2
    mid_x = width // 2
    if variant == "ambush":
        for x in range(width):
            grid[0][x] = "#"
        grid[min(height - 1, 1)][mid_x] = "c"
        grid[mid_y][mid_x] = "d"
    elif variant == "bridge":
        for y in range(height):
            for x in range(width):
                grid[y][x] = "#"
        for x in range(width):
            grid[mid_y][x] = "."
        grid[mid_y][mid_x] = "c"
        if width > 3:
            grid[mid_y][1] = "d"
    elif variant == "courtyard":
        for y in range(height):
            grid[y][0] = "#"
            grid[y][width - 1] = "#"
        for x in range(width):
            grid[0][x] = "#"
            grid[height - 1][x] = "#"
        grid[mid_y][mid_x] = "c"
        if mid_x > 1:
            grid[mid_y][mid_x - 1] = "d"
        if height > 2:
            grid[mid_y][0] = "."
    elif variant == "shore":
        for y in range(mid_y):
            for x in range(width):
                grid[y][x] = "d"
        grid[0][0] = "#"
        grid[mid_y][mid_x] = "c"
    else:
        grid[0][0] = "#"
        grid[mid_y][mid_x] = "c"
        if width > 2:
            grid[mid_y][1] = "d"
    return grid


def _dungeon_edges(count: int, variant: str) -> list[tuple[int, int]]:
    if variant == "vault":
        edges = [(1, room) for room in range(2, count + 1)]
    elif variant == "branch":
        edges = [(1, room) for room in range(2, count + 1)]
        if count >= 3:
            edges.append((2, 3))
    elif variant == "loop":
        edges = [(room, room + 1) for room in range(1, count)]
        if count > 2:
            edges.append((count, 1))
    elif variant == "cellar":
        edges = [(room, room + 1) for room in range(1, count)]
        if count >= 4:
            edges.append((2, count))
    else:
        edges = [(room, room + 1) for room in range(1, count)]
    return edges


def _dungeon(serial: int, variant: str) -> str:
    count = 3 + (serial % 4)
    place = SLOTS["place"][serial % len(SLOTS["place"])]
    edges = _dungeon_edges(count, variant)
    rooms = [
        f"Room {index} is the {ROOM_NAMES[index - 1]} at the {place}."
        if index == 1
        else f"Room {index} is the {ROOM_NAMES[index - 1]}."
        for index in range(1, count + 1)
    ]
    doors = [f"{left} to {right}" for left, right in edges] + [f"{right} to {left}" for left, right in edges]
    return "\n".join(
        (
            f"Dungeon map variant {variant} rooms {count} pass {serial}.",
            *rooms,
            "Doors " + ", ".join(doors) + ".",
            "Every room connects to the entry. A door returns the same way it was crossed.",
        )
    )


def render_map(family: str, serial: int) -> str:
    """One original map. The same serial always rebuilds the same variant."""
    if family not in FAMILIES:
        raise ValueError(f"unknown map family {family}")
    if isinstance(serial, bool) or not isinstance(serial, int) or serial < 0:
        raise ValueError("serial must be a non-negative int")
    variant = _variant(family, serial)
    if family == "adventure_map":
        return _adventure(serial, variant)
    width, height = _size(serial)
    if family == "sea_map":
        grid = _sea_grid(width, height, serial, variant)
        body = _paint(grid)
        legend = "Legend: ~ deep water elevation 0, - shallow water elevation 1, # land elevation 2, ^ rock elevation 3."
        title = f"Seamap variant {variant} grid {width}x{height} pass {serial}."
    elif family == "mountain_map":
        grid = _mountain_grid(width, height, serial, variant)
        body = _paint(grid)
        legend = "Legend: v valley elevation 0, . slope elevation 1, / rise elevation 2, ^ peak elevation 3."
        title = f"Mountain map variant {variant} grid {width}x{height} pass {serial}."
    elif family == "cave_map":
        grid, entrance = _cave_grid(width, height, serial, variant)
        body = _paint(grid)
        legend = (
            f"Entrance column {entrance[0]} row {entrance[1]}. "
            "Every floor and pool connects to the entrance. Walls are not walked."
        )
        title = f"Cave map variant {variant} grid {width}x{height} pass {serial}."
    elif family == "elevation_map":
        grid = _elevation_grid(width, height, variant)
        body = _digits(grid)
        legend = "Every cell is a height from 0 to 9. A walk reads the height and does not invent a second one."
        title = f"Elevation map variant {variant} grid {width}x{height} pass {serial}."
    elif family == "homebrew_map":
        grid = _homebrew_grid(width, height, variant)
        body = _paint(grid)
        legend = "Home is one cell. Every trail connects to home. The maker wrote the key, and a second key is not invented."
        title = f"Homebrew map variant {variant} grid {width}x{height} pass {serial}."
    elif family == "tabletop_map":
        grid = _tabletop_grid(width, height, variant)
        body = _paint(grid)
        legend = "Scale one square is five feet. Cover stops a shot and not a step. Difficult ground costs two. Blocking ground is not entered."
        title = f"Tabletop map variant {variant} grid {width}x{height} pass {serial}."
    else:
        return _dungeon(serial, variant)
    return "\n".join((title, body, legend))


def _bfs_floor(grid: list[list[str]], start: tuple[int, int]) -> dict[tuple[int, int], int]:
    height, width = len(grid), len(grid[0])
    seen = {start: 0}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in seen and grid[ny][nx] in {".", "~"}:
                seen[(nx, ny)] = seen[(x, y)] + 1
                queue.append((nx, ny))
    return seen


def _reach(grid: list[list[str]], start: tuple[int, int], walkable: set[str]) -> set[tuple[int, int]]:
    height, width = len(grid), len(grid[0])
    seen = {start}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in seen and grid[ny][nx] in walkable:
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen


def _room_reach(doors: list[tuple[int, int]], start: int = 1) -> set[int]:
    adjacent: dict[int, set[int]] = {}
    for left, right in doors:
        adjacent.setdefault(left, set()).add(right)
    seen = {start}
    queue: deque[int] = deque([start])
    while queue:
        room = queue.popleft()
        for nxt in adjacent.get(room, ()):
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def assess_map(text: str) -> dict[str, Any]:
    """Geometry and semantics for one generated map."""
    lines = text.splitlines()
    title = lines[0] if lines else ""
    family = ""
    if title.startswith("Seamap "):
        family = "sea_map"
    elif title.startswith("Mountain map "):
        family = "mountain_map"
    elif title.startswith("Cave map "):
        family = "cave_map"
    elif title.startswith("Elevation map "):
        family = "elevation_map"
    elif title.startswith("Adventure map "):
        family = "adventure_map"
    elif title.startswith("Homebrew map "):
        family = "homebrew_map"
    elif title.startswith("Tabletop map "):
        family = "tabletop_map"
    elif title.startswith("Dungeon map "):
        family = "dungeon_map"
    lowered = text.lower()
    reserved = any(name in lowered for name in RESERVED_NAMES)
    valid = False
    variant = ""
    if family in {"sea_map", "mountain_map", "cave_map", "elevation_map"} and not reserved:
        variant = title.split(" variant ")[1].split(" grid ")[0]
        size = title.split(" grid ")[1].split(" pass ")[0]
        width, height = (int(part) for part in size.split("x"))
        rows = lines[1 : 1 + height]
        legend = lines[1 + height] if len(lines) > 1 + height else ""
        if family == "elevation_map":
            grid = [[int(cell) for cell in row.split()] for row in rows]
            valid = (
                variant in VARIANTS[family]
                and len(grid) == height
                and all(len(row) == width and all(0 <= cell <= 9 for cell in row) for row in grid)
                and grid == _elevation_grid(width, height, variant)
                and "one height" in legend or "does not invent a second one" in legend
            )
        elif family == "sea_map":
            grid = [list(row) for row in rows]
            tiles = {cell for row in grid for cell in row}
            valid = (
                variant in VARIANTS[family]
                and len(grid) == height
                and all(len(row) == width for row in grid)
                and tiles <= set(SEA_ELEV)
                and any(cell in {"~", "-"} for row in grid for cell in row)
                and any(cell in {"#", "^"} for row in grid for cell in row)
                and "deep water elevation 0" in legend
                and "land elevation 2" in legend
            )
        elif family == "mountain_map":
            grid = [list(row) for row in rows]
            tiles = {cell for row in grid for cell in row}
            valid = (
                variant in VARIANTS[family]
                and len(grid) == height
                and all(len(row) == width for row in grid)
                and tiles <= set(MOUNTAIN_ELEV)
                and "^" in tiles
                and "v" in tiles
                and "peak elevation 3" in legend
                and "valley elevation 0" in legend
            )
        else:
            grid = [list(row) for row in rows]
            entrance_bits = legend.removeprefix("Entrance column ").split(" row ")
            column, row_rest = int(entrance_bits[0]), entrance_bits[1]
            row = int(row_rest.split(".", 1)[0])
            distances = _bfs_floor(grid, (column, row))
            floors = [(x, y) for y, cells in enumerate(grid) for x, cell in enumerate(cells) if cell in {".", "~"}]
            valid = (
                variant in VARIANTS[family]
                and len(grid) == height
                and all(len(cells) == width for cells in grid)
                and grid[row][column] in {".", "~"}
                and floors
                and set(floors) <= set(distances)
                and "Walls are not walked" in legend
            )
    elif family == "adventure_map" and not reserved:
        variant = title.split(" variant ")[1].split(" screens ")[0]
        letters = ("A", "B", "C", "D")
        screen_line = lines[3]
        elev = {}
        for letter in letters:
            piece = screen_line.split(f"Screen {letter} is ")[1].split(".")[0]
            elev[letter] = int(piece.split(" elevation ")[1])
        raw_links = lines[4].removeprefix("Links ").removesuffix(".").split(", ")
        links = tuple(tuple(part.split(" ")) for part in raw_links)
        stairs = set()
        if lines[5] != "Stairs none.":
            stairs = {part.strip() for part in lines[5].removeprefix("Stairs ").removesuffix(".").split(", ")}
        paired = {(right, OPPOSITE[direction], left) for left, direction, right in links}
        gaps = {f"{left} {direction}" for left, direction, right in links if abs(elev[left] - elev[right]) > 1}
        valid = (
            variant in VARIANTS[family]
            and lines[1] == "AB"
            and lines[2] == "CD"
            and set(links) == paired
            and stairs == gaps
            and "return" in lines[6]
        )
    elif family == "homebrew_map" and not reserved:
        variant = title.split(" variant ")[1].split(" grid ")[0]
        size = title.split(" grid ")[1].split(" pass ")[0]
        width, height = (int(part) for part in size.split("x"))
        rows = lines[1 : 1 + height]
        grid = [list(row) for row in rows]
        homes = [(x, y) for y, cells in enumerate(grid) for x, cell in enumerate(cells) if cell == "H"]
        keys = [(x, y) for y, cells in enumerate(grid) for x, cell in enumerate(cells) if cell == "K"]
        legend = lines[1 + height] if len(lines) > 1 + height else ""
        reached = _reach(grid, homes[0], WALK_HOME) if homes else set()
        trails = [(x, y) for y, cells in enumerate(grid) for x, cell in enumerate(cells) if cell in WALK_HOME]
        valid = (
            variant in VARIANTS[family]
            and len(grid) == height
            and all(len(cells) == width for cells in grid)
            and {cell for cells in grid for cell in cells} <= HOMEBREW_TILES
            and len(homes) == 1
            and len(keys) == 1
            and set(trails) <= reached
            and "Home is one cell" in legend
            and "second key is not invented" in legend
        )
    elif family == "tabletop_map" and not reserved:
        variant = title.split(" variant ")[1].split(" grid ")[0]
        size = title.split(" grid ")[1].split(" pass ")[0]
        width, height = (int(part) for part in size.split("x"))
        rows = lines[1 : 1 + height]
        grid = [list(row) for row in rows]
        legend = lines[1 + height] if len(lines) > 1 + height else ""
        walkable = [(x, y) for y, cells in enumerate(grid) for x, cell in enumerate(cells) if cell in WALK_TABLE]
        cover = any(cell == "c" for cells in grid for cell in cells)
        reached = _reach(grid, walkable[0], WALK_TABLE) if walkable else set()
        valid = (
            variant in VARIANTS[family]
            and len(grid) == height
            and all(len(cells) == width for cells in grid)
            and {cell for cells in grid for cell in cells} <= TABLETOP_TILES
            and cover
            and walkable
            and set(walkable) <= reached
            and "Scale one square is five feet." in legend
            and "Cover stops a shot and not a step." in legend
        )
    elif family == "dungeon_map" and not reserved:
        variant = title.split(" variant ")[1].split(" rooms ")[0]
        count = int(title.split(" rooms ")[1].split(" pass ")[0])
        rooms = lines[1 : 1 + count]
        door_line = lines[1 + count] if len(lines) > 1 + count else ""
        legend = lines[2 + count] if len(lines) > 2 + count else ""
        raw = door_line.removeprefix("Doors ").removesuffix(".")
        doors = []
        if raw:
            for part in raw.split(", "):
                left, arrow, right = part.split(" ")
                if arrow == "to":
                    doors.append((int(left), int(right)))
        paired = {(right, left) for left, right in doors}
        valid = (
            variant in VARIANTS[family]
            and len(rooms) == count
            and rooms[0].startswith("Room 1 is the entry")
            and all(rooms[index - 1].startswith(f"Room {index} is the {ROOM_NAMES[index - 1]}") for index in range(1, count + 1))
            and set(doors) == paired
            and _room_reach(doors) == set(range(1, count + 1))
            and "Every room connects to the entry." in legend
            and "same way" in legend
        )
    return {"valid": bool(valid), "family": family, "variant": variant, "reserved_name": reserved}


def map_holdouts() -> tuple[str, ...]:
    rows = [render_map(family, HOLDOUT_SERIAL + offset) for family in FAMILIES for offset in (0, 1)]
    if len(rows) != len(set(rows)):
        raise RuntimeError("map holdout collided")
    return tuple(rows)


def validate_maps() -> dict[str, int]:
    banned = banned_windows(DENYLIST)
    checked = 0
    for family in FAMILIES:
        for serial in (0, 1, HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1):
            text = render_map(family, serial)
            report = assess_map(text)
            if not report["valid"] or leaks(text, banned):
                raise ValueError(f"{family} serial {serial} is not a valid original map")
            checked += 1
    return {"families": len(FAMILIES), "checked": checked}


def iter_training_maps(
    map_budget: int,
    *,
    start: int = 0,
    families: tuple[str, ...] | None = None,
    family_budget: int | None = None,
) -> Iterator[tuple[str, str]]:
    """Yield original maps until the map budget is met. Holdout serials never appear."""
    if isinstance(map_budget, bool) or not isinstance(map_budget, int) or map_budget < 1:
        raise ValueError("map_budget must be a positive int")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ValueError("start must be a non-negative int")
    chosen = FAMILIES if families is None else tuple(families)
    if not chosen or any(name not in FAMILIES for name in chosen):
        raise ValueError("families must be known map families")
    if family_budget is not None and (isinstance(family_budget, bool) or not isinstance(family_budget, int) or family_budget < 1):
        raise ValueError("family_budget must be a positive int")
    validate_maps()
    banned = banned_windows(DENYLIST)
    reserved = set(map_holdouts())
    produced = 0
    counter = 0
    skips = 0
    counts = {name: 0 for name in chosen}
    while produced < map_budget:
        family = chosen[counter % len(chosen)]
        if family_budget is not None and counts[family] >= family_budget:
            if all(counts[name] >= family_budget for name in chosen):
                break
            counter += 1
            continue
        serial = training_serial(counter)
        counter += 1
        text = render_map(family, serial)
        if leaks(text, banned) or text in reserved or not assess_map(text)["valid"]:
            skips += 1
            if skips > 1000:
                raise RuntimeError("map training kept colliding with reserved text")
            continue
        skips = 0
        produced += 1
        counts[family] += 1
        if produced <= start:
            continue
        yield family, text


def train_map_budget(
    *,
    map_budget: int = BILLION_MAPS,
    peak_lr: float = 3e-5,
    hidden: int = 256,
    source: Path | str | None = Path(".skeleton/game-coherent-1m/checkpoint.pt"),
    checkpoint_dir: Path | str = Path(".skeleton/game-maps-billion"),
    chunk_maps: int = 8,
    slack: float = 2e-4,
    expected_digest: str | None = MILLION_WORD_DIGEST,
    plateau_rejects: int | None = None,
    max_seconds: float | None = None,
    persist_every: int = 2048,
    families: tuple[str, ...] | None = None,
    family_budget: int | None = None,
    selection: str = "map-billion",
    ledger_path: Path | str | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Train on original map variants until the budget, a time cap, or a reject plateau.

    A step is kept only when the mean holdout rises and no track, including
    the map grids, falls past the slack. The source checkpoint is not replaced.
    An existing destination checkpoint resumes the same budget.
    """
    if isinstance(map_budget, bool) or not isinstance(map_budget, int) or map_budget < 1:
        raise ValueError("map_budget must be a positive int")
    if not isinstance(peak_lr, (int, float)) or isinstance(peak_lr, bool) or not 0.0 < float(peak_lr) <= 1.0:
        raise ValueError("peak_lr must be in (0, 1]")
    if isinstance(chunk_maps, bool) or not isinstance(chunk_maps, int) or chunk_maps < 1:
        raise ValueError("chunk_maps must be a positive int")
    if plateau_rejects is not None and (isinstance(plateau_rejects, bool) or plateau_rejects < 1):
        raise ValueError("plateau_rejects must be a positive int")
    if max_seconds is not None and (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or max_seconds <= 0):
        raise ValueError("max_seconds must be positive")
    if isinstance(persist_every, bool) or not isinstance(persist_every, int) or persist_every < 1:
        raise ValueError("persist_every must be a positive int")
    chosen = FAMILIES if families is None else tuple(families)
    if not chosen or any(name not in FAMILIES for name in chosen):
        raise ValueError("families must be known map families")
    if family_budget is not None and (isinstance(family_budget, bool) or not isinstance(family_budget, int) or family_budget < 1):
        raise ValueError("family_budget must be a positive int")
    if not isinstance(selection, str) or not selection:
        raise ValueError("selection must be a non-empty string")
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    ckpt_path = root / "checkpoint.pt"
    torch.manual_seed(11)
    model = ByteRNN(hidden)
    parameters = [item for item in model.parameters() if item.requires_grad]
    source_digest = None
    maps = 0
    maps_kept = 0
    byte_count = 0
    family_counts: dict[str, int] = {}
    family_kept: dict[str, int] = {}
    elapsed_before = 0.0
    seen: set[str] = set()
    resumed = False
    if ckpt_path.exists():
        loaded = torch.load(ckpt_path, map_location="cpu", weights_only=True)
        if int(loaded.get("hidden", -1)) != hidden:
            raise ValueError("checkpoint hidden size does not match")
        model.load_state_dict(loaded["best_state"])
        _pin(model)
        maps = int(loaded.get("maps_done", 0))
        maps_kept = int(loaded.get("maps_kept", 0))
        byte_count = int(loaded.get("bytes_trained", 0))
        elapsed_before = float(loaded.get("elapsed", 0.0))
        source_digest = loaded.get("source_digest")
        seen = set(loaded.get("families") or [])
        family_counts = {str(key): int(value) for key, value in (loaded.get("family_counts") or {}).items()}
        family_kept = {str(key): int(value) for key, value in (loaded.get("family_kept") or {}).items()}
        resumed = True
    elif source is not None:
        loaded = torch.load(source, map_location="cpu", weights_only=True)
        if int(loaded["hidden"]) != hidden:
            raise ValueError("source checkpoint hidden size does not match")
        model.load_state_dict(loaded["best_state"])
        _pin(model)
        source_digest = network_digest(model)
        if expected_digest is not None and source_digest != expected_digest:
            raise ValueError("source checkpoint does not match the expected digest")
    tracks = track_holdouts()
    tracks["maps"] = map_holdouts()
    best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    best_scores = _scores(model, tracks)
    ratchet = AdaptiveRatchet(min_scale=1.0, slack=slack, slack_cap=slack, margin_cap=1e-5)
    if resumed:
        snap = loaded.get("ratchet") or {}
        for key in ("margin", "scale", "ceiling", "slack", "accepts", "rejects", "reject_streak"):
            if key in snap:
                setattr(ratchet, key, snap[key])
        if snap.get("recent"):
            ratchet.recent = deque((int(item) for item in snap["recent"]), maxlen=16)
        ratchet.stall = int(loaded.get("stall", 0))
    opt = _fresh_optimizer(parameters, float(peak_lr))
    started = time.perf_counter()
    batch: list[tuple[str, str]] = []
    reason: str | None = None
    model.train()

    def _flush() -> None:
        nonlocal maps, maps_kept, byte_count, best_state, best_scores, opt
        if not batch:
            return
        texts = [item[1] for item in batch]
        origin = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        opt.param_groups[0]["lr"] = float(peak_lr) * ratchet.scale
        loss = _batch_loss(model, texts)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(parameters, GRAD_CLIP)
        opt.step()
        _pin(model)
        value = float(loss.detach())
        count = len(batch)
        if not math.isfinite(value):
            model.load_state_dict(origin)
            _pin(model)
            opt = _fresh_optimizer(parameters, float(peak_lr))
            ratchet.rejects += 1
            ratchet.stall += 1
        else:
            after = _scores(model, tracks)
            if ratchet.observe(best_scores, after):
                best_scores = after
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
                maps_kept += count
                for family, _text in batch:
                    family_kept[family] = family_kept.get(family, 0) + 1
            else:
                model.load_state_dict(origin)
                _pin(model)
                opt = _fresh_optimizer(parameters, float(peak_lr))
        maps += count
        for family, text in batch:
            family_counts[family] = family_counts.get(family, 0) + 1
            byte_count += len(text.encode("utf-8"))
        batch.clear()

    def _elapsed() -> float:
        return elapsed_before + (time.perf_counter() - started)

    def _stop() -> str | None:
        found = training_stop(maps, map_budget, ratchet.stall, plateau_rejects)
        if found is not None:
            return found
        if max_seconds is not None and _elapsed() >= float(max_seconds):
            return "time"
        return None

    def _save_checkpoint() -> None:
        payload = {
            "best_state": best_state,
            "hidden": hidden,
            "maps_done": maps,
            "maps_kept": maps_kept,
            "bytes_trained": byte_count,
            "source_digest": source_digest,
            "goal": map_budget,
            "elapsed": _elapsed(),
            "ratchet": ratchet.snapshot(),
            "stall": ratchet.stall,
            "families": sorted(seen),
            "family_counts": family_counts,
            "family_kept": family_kept,
        }
        tmp = ckpt_path.with_suffix(".tmp")
        torch.save(payload, tmp)
        os.replace(tmp, ckpt_path)

    if maps < map_budget:
        for family, text in iter_training_maps(
            map_budget,
            start=maps,
            families=chosen,
            family_budget=family_budget,
        ):
            seen.add(family)
            batch.append((family, text))
            if len(batch) >= chunk_maps:
                _flush()
                reason = _stop()
                if reason is not None:
                    break
                if maps > 0 and maps % persist_every == 0:
                    _save_checkpoint()
                    if log is not None:
                        print(
                            f"maps={maps} kept={maps_kept} accepts={ratchet.accepts} rejects={ratchet.rejects} sec={_elapsed():.1f}",
                            file=log,
                            flush=True,
                        )
    if batch and reason is None:
        _flush()
        reason = _stop()
    if reason is None:
        reason = "budget" if maps >= map_budget else "stopped"
    model.load_state_dict(best_state)
    _pin(model)
    official = NumpyRecurrentLM(
        model_id="game-corpus-199",
        config=NeuralLMConfig(hidden_size=hidden, seed=11, dtype="float64"),
        parameters=model.numpy_parameters(),
    )
    official_scores = {name: float(official.loss(texts)) for name, texts in tracks.items()}
    seconds = round(_elapsed(), 3)
    forecast = budget_forecast(max(maps, 1), max(seconds, 1e-6), map_budget)
    _save_checkpoint()
    receipt = {
        "schema": SCHEMA,
        "kind": "byte-language-model",
        "language": "english",
        "map_budget": map_budget,
        "maps_trained": maps,
        "maps_kept": maps_kept,
        "families": sorted(seen),
        "family_counts": family_counts,
        "family_kept": family_kept,
        "per_family_budget": None if family_budget is None else int(family_budget),
        "stop_reason": reason,
        "budget_met": bool(forecast["budget_met"]),
        "maps_per_second": forecast["words_per_second"],
        "words_per_second": forecast["words_per_second"],
        "projected_seconds": forecast["projected_seconds"],
        "max_seconds": None if max_seconds is None else float(max_seconds),
        "goal": map_budget,
        "bytes_trained": byte_count,
        "cycle_start": 0,
        "cycle_bytes": byte_count,
        "words_trained": maps,
        "hidden_size": hidden,
        "peak_lr": float(peak_lr),
        "adamw": {
            "lr": float(peak_lr),
            "betas": list(ADAMW_BETAS),
            "eps": ADAMW_EPS,
            "weight_decay": ADAMW_WEIGHT_DECAY,
            "grad_clip": GRAD_CLIP,
        },
        "torch_best_tracks": best_scores,
        "official_tracks": official_scores,
        "ratchet": ratchet.snapshot(),
        "source_digest": source_digest,
        "model_digest": official.model_digest,
        "seconds": seconds,
        "promotion": False,
        "service_checkpoint_touched": False,
        "byte_loss_is_gameplay_quality": False,
        "selection": selection,
        "loss_focus": None,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if ledger_path is not None:
        _append_ledger(Path(ledger_path), receipt)
    if log is not None:
        print(
            f"done maps={maps} kept={maps_kept} stop={reason} accepts={ratchet.accepts} rejects={ratchet.rejects}",
            file=log,
            flush=True,
        )
    return receipt
