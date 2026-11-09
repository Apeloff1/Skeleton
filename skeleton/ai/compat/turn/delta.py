"""GB-44 playable delta. Identical cards are a stamp, not a rebuild."""

from __future__ import annotations

_KEYS = ("ticks", "extract_count", "warp_count")


def delta(before: dict, after: dict) -> dict:
    moved = {}
    for key in _KEYS:
        left = int(before.get(key) or 0)
        right = int(after.get(key) or 0)
        moved[key] = right - left
    stamp = 0 if any(value != 0 for value in moved.values()) else 1
    return {
        "kind": "delta",
        "moved": moved,
        "stamp": stamp,
        "rebuild": 0,
        "stored_prose": 0,
    }
