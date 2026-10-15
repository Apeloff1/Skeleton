"""Deterministic RGB state telemetry for original-game reference episodes.

The studio's gameplay state is the only pixel source. This is NOT a rendered
game world or hardware emulator framebuffer; it depicts reproducible scalar
observations and explicitly recorded source-state occupancy. An application
must keep its 'telemetry' label rather than claiming native rendering.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import math
from typing import Mapping

WIDTH = 96
HEIGHT = 64
CHANNELS = 3
BYTE_LIMIT = WIDTH * HEIGHT * CHANNELS
_SCHEMA = "skeleton.game.studio_state_telemetry.v1"
_COLORS = (
    (61, 178, 227), (114, 210, 151), (235, 189, 100),
    (231, 123, 145), (171, 146, 239), (109, 217, 201),
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
    x1, y1 = max(0,x), max(0,y)
    x2, y2 = min(WIDTH,x+w), min(HEIGHT,y+h)
    for row in range(y1,y2):
        start = (row * WIDTH + x1) * CHANNELS
        buffer[start:start + (x2-x1) * CHANNELS] = rgb * (x2-x1)


def render_studio_state_telemetry(
    editor: str,
    observation: Mapping[str, float],
    state: Mapping[str, object],
    *,
    source_session_digest: str,
    accepted_action_count: int,
) -> dict[str, object]:
    if (
        type(editor) is not str or not editor or len(editor) > 64
        or type(source_session_digest) is not str
        or len(source_session_digest) != 64
        or any(c not in "0123456789abcdef" for c in source_session_digest)
        or type(accepted_action_count) is not int
        or not 0 <= accepted_action_count <= 128
        or set(observation) != set(_KEYS)
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
        "width": WIDTH, "height": HEIGHT, "format": "rgb24",
        "pixels_base64": base64.b64encode(raw).decode("ascii"),
        "pixel_digest": sha256(raw).hexdigest(),
        "source_session_digest": source_session_digest,
        "accepted_action_count": turns,
        "metric_keys": list(_KEYS),
        "native_hardware_verified": False,
        "real_game_world_framebuffer": False,
        "semantic_note": "derived reference telemetry; not game-world pixels or audio",
    }


__all__ = ["WIDTH","HEIGHT","BYTE_LIMIT","render_studio_state_telemetry"]
