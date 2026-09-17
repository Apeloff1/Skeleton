"""Named stealth stances. LOS + heat + hunt."""

from __future__ import annotations

from typing import Any


class StealthPackError(ValueError):
    pass


STANCE: dict[str, tuple[int, int]] = {
    "crouch": (-1, 0),
    "prone": (-2, 0),
    "walk": (0, 0),
    "sprint": (2, 1),
    "hold": (-1, 0),
    "bait": (1, 0),
    "vent": (0, 1),
    "fog": (-1, 0),
    "crowd": (1, 1),
    "quiet": (-2, 0),
    "dream": (0, 0),
    "extract": (0, 0),
}


def apply(state: dict[str, Any], name: str, seen: bool) -> dict[str, Any]:
    if name not in STANCE:
        raise StealthPackError(name)
    da, dh = STANCE[name]
    nxt = dict(state)
    nxt["stance"] = name
    nxt["alert"] = max(0, int(nxt.get("alert", 0)) + (da if seen else -1))
    nxt["heat"] = max(0, int(nxt.get("heat", 0)) + dh)
    nxt["stored_prose"] = 0
    return nxt
