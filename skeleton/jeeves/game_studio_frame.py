"""Original state scenes and RGB telemetry for reference-game episodes.

Known maze, farm and RPG scenes project actual canonical replay state through
original bounded drawing rules. Other engines retain labelled scalar telemetry.
Neither path is a hardware emulator framebuffer or commercial-game art/audio.
"""

from __future__ import annotations

import base64
import json
import math
import struct
import zlib
from collections.abc import Mapping
from hashlib import sha256

WIDTH = 96
HEIGHT = 64
CHANNELS = 3
BYTE_LIMIT = WIDTH * HEIGHT * CHANNELS
_SCHEMA = "skeleton.game.studio_state_telemetry.v1"
_COLORS = (
    (61, 178, 227),
    (114, 210, 151),
    (235, 189, 100),
    (231, 123, 145),
    (171, 146, 239),
    (109, 217, 201),
    (222, 171, 219),
)
_KEYS = ("progress", "score", "resources", "health", "time", "success", "failure")


def _safe(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        return 0.0
    return max(-1000.0, min(1000.0, float(value)))


def _level(value: float) -> float:
    # Symmetric squash gives visible changes across high-variance real values
    # while bounding the reference display for all 43 source simulators.
    return 0.5 + 0.5 * (value / (1.0 + abs(value)))


def _rect(buffer: bytearray, x: int, y: int, w: int, h: int, color: tuple[int, int, int]) -> None:
    if w <= 0 or h <= 0:
        return
    rgb = bytes(color)
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(WIDTH, x + w), min(HEIGHT, y + h)
    for row in range(y1, y2):
        start = (row * WIDTH + x1) * CHANNELS
        buffer[start : start + (x2 - x1) * CHANNELS] = rgb * (x2 - x1)


def render_studio_state_telemetry(
    editor: str,
    observation: Mapping[str, float],
    state: Mapping[str, object],
    *,
    source_session_digest: str,
    accepted_action_count: int,
) -> dict[str, object]:
    if (
        type(editor) is not str
        or not editor
        or len(editor) > 64
        or type(source_session_digest) is not str
        or len(source_session_digest) != 64
        or any(c not in "0123456789abcdef" for c in source_session_digest)
        or type(accepted_action_count) is not int
        or not 0 <= accepted_action_count <= 128
        or not set(_KEYS).issubset(observation)
    ):
        raise ValueError("exact game-origin replay telemetry required")
    pixels = bytearray((13, 20, 31) * (WIDTH * HEIGHT))
    seed = sha256(editor.encode("ascii")).digest()
    # Authored engine identity, not artificial world coordinates or textures.
    _rect(pixels, 0, 0, WIDTH, 7, (28, 41, 59))
    for index in range(8):
        if seed[index] & 1:
            _rect(pixels, 4 + index * 11, 2, 8, 3, _COLORS[index % len(_COLORS)])
    # Each bar is sourced from the re-executed engine observation.
    for index, key in enumerate(_KEYS):
        y = 10 + index * 7
        color = _COLORS[index]
        _rect(pixels, 9, y, WIDTH - 18, 4, (35, 49, 64))
        amount = max(0, min(WIDTH - 18, int(_level(_safe(observation[key])) * (WIDTH - 18))))
        if amount:
            _rect(pixels, 9, y, amount, 4, color)
        if _safe(observation[key]) < 0:
            _rect(pixels, 6, y, 2, 4, (232, 114, 99))
    # Exact observed gameplay event counter, not fictitious animation output.
    # This marker advances when the replay ledger advances.
    turns = max(0, min(128, accepted_action_count))
    _rect(pixels, 0, 61, WIDTH, 3, (24, 38, 53))
    _rect(pixels, 0, 61, min(WIDTH, turns * WIDTH // 128), 3, (108, 181, 226))
    raw = bytes(pixels)
    if len(raw) != BYTE_LIMIT:
        raise RuntimeError("reference telemetry pixel buffer differs from declared dimensions")
    return {
        "schema_version": _SCHEMA,
        "render_kind": "reference_state_telemetry_raster",
        "width": WIDTH,
        "height": HEIGHT,
        "format": "rgb24",
        "pixels_base64": base64.b64encode(raw).decode("ascii"),
        "pixel_digest": sha256(raw).hexdigest(),
        "source_session_digest": source_session_digest,
        "accepted_action_count": turns,
        "metric_keys": list(_KEYS),
        "native_hardware_verified": False,
        "real_game_world_framebuffer": False,
        "semantic_note": "derived reference telemetry; not game-world pixels or audio",
    }


def render_studio_scene(
    editor: str,
    state: Mapping[str, object],
    settings: Mapping[str, object],
    *,
    source_session_digest: str,
) -> dict[str, object] | None:
    """Render original scene diagrams from exact replay state, never ROM art.

    Maze cells use the actual canonical collision predicate. Farm sectors use
    their actual crop/age/moisture/soil. RPG panels represent actual party and
    quest state; they deliberately make no spatial-world rendering claim.
    """
    if editor not in {"maze", "farming", "rpg"}:
        return None
    if (
        not isinstance(state, Mapping)
        or not isinstance(settings, Mapping)
        or type(source_session_digest) is not str
        or len(source_session_digest) != 64
        or any(char not in "0123456789abcdef" for char in source_session_digest)
    ):
        raise ValueError("bounded actual studio scene state required")
    encoded = json.dumps(
        dict(state), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()
    if len(encoded) > 131072:
        raise ValueError("actual studio state exceeds scene projection bound")
    width, height = 192, 128
    pixels = bytearray((18, 28, 39) * width * height)

    def rect(x, y, w, h, color):
        left, top = max(0, int(x)), max(0, int(y))
        right, bottom = min(width, int(x + w)), min(height, int(y + h))
        if right <= left or bottom <= top:
            return
        for row in range(top, bottom):
            offset = (row * width + left) * 3
            pixels[offset : offset + (right - left) * 3] = bytes(color) * (right - left)

    def bar(x, y, w, value, color):
        rect(x, y, w, 5, (38, 49, 61))
        rect(x, y, int(w * min(1, max(0, value))), 5, color)

    summary: dict[str, object] = {}
    if editor == "maze":
        from skeleton.ai.game_builder.advanced_world_rpg_runtime import _maze_wall

        columns, rows = min(settings["width"], 20), min(settings["height"], 12)
        px, py = state["position"]
        start_x = max(0, min(settings["width"] - columns, px - columns // 2))
        start_y = max(0, min(settings["height"] - rows, py - rows // 2))
        cell = min(9, 180 // columns, 108 // rows)
        origin_x, origin_y = (width - columns * cell) // 2, 6
        visited = {tuple(point) for point in state["surveyed"]}
        for row in range(rows):
            for column in range(columns):
                x, y = start_x + column, start_y + row
                wall = _maze_wall(x, y, settings, state["seed"], state["level"])
                color = (94, 106, 113) if wall else (58, 80, 69) if (x, y) in visited else (32, 48, 46)
                rect(origin_x + column * cell, origin_y + row * cell, cell - 1, cell - 1, color)
        for point, color, visible in (
            (state["exit"], (119, 221, 180), True),
            (state["key_position"], (246, 207, 89), not state["has_key"]),
            (state["position"], (106, 183, 249), True),
        ):
            if visible and start_x <= point[0] < start_x + columns and start_y <= point[1] < start_y + rows:
                rect(
                    origin_x + (point[0] - start_x) * cell + 1,
                    origin_y + (point[1] - start_y) * cell + 1,
                    max(1, cell - 3),
                    max(1, cell - 3),
                    color,
                )
        bar(8, 116, 80, state["health"] / max(1, state["max_health"]), (225, 116, 120))
        bar(104, 116, 80, state["completed_levels"] / max(1, settings["levels"]), (126, 209, 164))
        summary = {
            "position": list(state["position"]),
            "exit": list(state["exit"]),
            "key_position": list(state["key_position"]),
            "has_key": state["has_key"],
            "camera_cell_origin": [start_x, start_y],
            "health": state["health"],
            "completed_levels": state["completed_levels"],
        }
    elif editor == "farming":
        for index, plot in enumerate(state["plots"]):
            x, y = 8 + index % 2 * 94, 7 + index // 2 * 49
            rect(x, y, 86, 42, (94 + plot["soil"] * 8, 64 + plot["soil"] * 5, 42))
            for stripe in range(3):
                rect(x + 4, y + 5 + stripe * 9, 78, 2, (67, 49, 36))
            if plot["crop"] >= 0:
                goal = max(1, settings["growth_days"] // (plot["crop"] + 2))
                growth = min(1, plot["age"] / goal)
                for stalk in range(5):
                    stem_x = x + 10 + stalk * 14
                    stem_h = 5 + int(growth * 18)
                    rect(stem_x, y + 30 - stem_h, 3, stem_h, (110, 192, 93))
                    if growth >= 1:
                        rect(stem_x - 2, y + 27 - stem_h, 7, 5, (239, 188, 94))
            bar(x + 4, y + 35, 75, plot["moisture"] / 5, (93, 177, 226))
            for pest in range(min(3, plot["pests"])):
                rect(x + 72 - pest * 5, y + 3, 3, 3, (231, 114, 116))
        bar(8, 112, 52, state["coins"] / 80, (242, 200, 101))
        bar(70, 112, 52, state["seeds"] / 8, (119, 205, 148))
        bar(132, 112, 52, state["water"] / 12, (93, 177, 226))
        summary = {
            key: state[key]
            for key in (
                "day",
                "season",
                "weather",
                "coins",
                "seeds",
                "water",
                "harvest_stock",
                "harvested",
                "contracts_completed",
                "plots",
            )
        }
    else:
        party = state["party"]
        for index, member in enumerate(party):
            x = 8 + index * (176 // max(1, len(party)))
            rect(x, 12, max(12, 168 // max(1, len(party))), 39, (48, 68, 93))
            rect(x + 6, 18, 8, 12, (124, 179, 226))
            bar(x + 4, 42, max(6, 160 // max(1, len(party))), member["hp"] / 8, (133, 207, 153))
        stages = ("unknown", "offered", "active", "completed")
        for index, stage in enumerate(stages):
            x = 10 + index * 46
            rect(x, 69, 32, 18, (229, 188, 99) if state["quest_state"] == stage else (54, 67, 80))
            if index < 3:
                rect(x + 34, 77, 10, 2, (113, 139, 163))
        bar(8, 103, 52, state["rations"] / 6, (125, 207, 149))
        bar(70, 103, 52, state["gold"] / 20, (238, 193, 90))
        bar(132, 103, 52, state["enemy_hp"] / 10, (227, 126, 136))
        summary = {
            key: state[key]
            for key in (
                "region",
                "party",
                "quest_state",
                "quest_evidence",
                "enemy_hp",
                "rations",
                "gold",
                "quests_completed",
            )
        }
    raw = bytes(pixels)

    def chunk(name, data):
        return (
            struct.pack(">I", len(data))
            + name
            + data
            + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
        )

    scanlines = b"".join(b"\x00" + raw[row * width * 3 : (row + 1) * width * 3] for row in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines, 6))
        + chunk(b"IEND", b"")
    )
    return {
        "schema_version": "skeleton.game.studio_scene_preview.v1",
        "render_kind": "original_reference_scene_projection",
        "width": width,
        "height": height,
        "format": "png",
        "data_uri": "data:image/png;base64," + base64.b64encode(png).decode("ascii"),
        "png_digest": sha256(png).hexdigest(),
        "pixel_digest": sha256(raw).hexdigest(),
        "source_session_digest": source_session_digest,
        "source_state_digest": sha256(encoded).hexdigest(),
        "scene_state": summary,
        "native_hardware_verified": False,
        "real_game_world_framebuffer": False,
        "semantic_note": "Original rendered diagram of exact reference-game state, not hardware or commercial-game pixels/audio",
    }


__all__ = ["BYTE_LIMIT", "HEIGHT", "WIDTH", "render_studio_scene", "render_studio_state_telemetry"]
