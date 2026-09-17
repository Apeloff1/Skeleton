"""Deterministic room layouts. Rects and door sockets. Seeded, not copied."""

from __future__ import annotations

import hashlib
from typing import Any


MAX_ROOMS = 16
TILE = 32


class LayoutError(ValueError):
    """Layout contract violation."""


def _roll(seed: int, label: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{seed}:{label}:lay".encode("utf-8")).digest()[:8], "big")


def room(seed: int, index: int, kind: str) -> dict[str, Any]:
    if index < 0 or index >= MAX_ROOMS:
        raise LayoutError("room index out of range")
    width = 8 + (_roll(seed, f"w:{index}") % 5)
    height = 6 + (_roll(seed, f"h:{index}") % 4)
    sockets = []
    if index > 0:
        sockets.append({"dir": "w", "x": 0, "y": height // 2})
    if kind != "extract":
        sockets.append({"dir": "e", "x": width, "y": height // 2})
    if _roll(seed, f"n:{index}") % 3 == 0:
        sockets.append({"dir": "n", "x": width // 2, "y": 0})
    piles = 1 + (_roll(seed, f"p:{index}") % 3)
    scrap = []
    for slot in range(piles):
        scrap.append({
            "x": 1 + (_roll(seed, f"sx:{index}:{slot}") % max(1, width - 2)),
            "y": 1 + (_roll(seed, f"sy:{index}:{slot}") % max(1, height - 2)),
        })
    heat_node = {"x": width // 2, "y": height // 2, "kind": kind}
    return {
        "id": f"r{index}",
        "kind": kind,
        "w": width,
        "h": height,
        "px": width * TILE,
        "py": height * TILE,
        "sockets": sockets,
        "scrap": scrap,
        "heat": heat_node,
        "stored_prose": 0,
    }


def campus(seed: int, kinds: list[str]) -> dict[str, Any]:
    if len(kinds) < 2 or len(kinds) > MAX_ROOMS:
        raise LayoutError("campus size out of range")
    rooms = [room(seed, index, kind) for index, kind in enumerate(kinds)]
    origin_x = 0
    placed = []
    for item in rooms:
        row = dict(item)
        row["ox"] = origin_x
        row["oy"] = 0
        origin_x += row["px"] + TILE
        placed.append(row)
    return {
        "kind": "campus",
        "seed": int(seed),
        "n": len(placed),
        "rooms": placed,
        "width_px": origin_x,
        "stored_prose": 0,
    }
