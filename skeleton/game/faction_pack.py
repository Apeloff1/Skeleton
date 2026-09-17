"""Named factions. Standing only."""

from __future__ import annotations

from typing import Any


class FactionPackError(ValueError):
    pass


FACTIONS = (
    "ash", "vent", "lock", "coil", "dream", "fog", "stair", "shaft",
    "crowd", "quiet", "seal", "warp", "mesh", "clip", "hunt", "bait",
)


def stand(state: dict[str, Any], name: str, delta: int) -> dict[str, Any]:
    if name not in FACTIONS:
        raise FactionPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("faction") or {})
    cur[name] = max(-8, min(8, int(cur.get(name, 0)) + int(delta)))
    nxt["faction"] = cur
    nxt["stored_prose"] = 0
    return nxt
