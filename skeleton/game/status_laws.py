"""Named status laws. Table caps and decay. No stored prose."""

from __future__ import annotations

from typing import Any

from skeleton.game.law_names import STATUS


class StatusLawError(ValueError):
    pass


LAWS: dict[str, tuple[int, int, str]] = {
    "burn": (8, -1, "heat"),
    "chill": (6, -1, "heat"),
    "bleed": (10, -1, "hp"),
    "ward": (8, -1, "heat"),
    "daze": (4, -1, "alert"),
    "focus": (6, -1, "xp"),
    "fear": (8, -1, "alert"),
    "lure": (6, -1, "bait"),
    "lockshock": (4, -1, "key"),
    "vent": (12, -2, "heat"),
    "ash": (9, -1, "sleep"),
    "fogmind": (8, -1, "los"),
    "coilpulse": (5, -1, "coil"),
    "scrapcut": (3, -1, "hp"),
    "overheat": (16, -2, "heat"),
    "dreamlag": (10, -1, "sleep"),
    "extractready": (1, 0, "extracted"),
    "stalkmark": (12, -1, "alert"),
    "jam": (6, -1, "occupancy"),
    "spill": (4, -1, "occupancy"),
    "quiet": (8, -1, "alert"),
    "loud": (6, -1, "alert"),
    "hungry": (10, -1, "scrap"),
    "fed": (4, -1, "hp"),
    "keyed": (2, 0, "key"),
    "baited": (4, -1, "bait"),
    "sleepless": (14, -1, "sleep"),
    "rested": (6, -1, "sleep"),
    "tracked": (10, -1, "alert"),
    "hidden": (8, -1, "alert"),
    "pressured": (12, -2, "heat"),
    "relieved": (4, -1, "heat"),
    "warped": (1, 0, "warp"),
    "sealed": (1, 0, "digest"),
    "doctored": (4, -1, "mass"),
    "clipped": (2, 0, "mass"),
}


def apply(state: dict[str, Any], name: str, stacks: int = 1) -> dict[str, Any]:
    if name not in LAWS:
        raise StatusLawError(name)
    cap, _decay, _stat = LAWS[name]
    nxt = dict(state)
    cur = dict(nxt.get("status") or {})
    cur[name] = min(cap, max(0, int(cur.get(name, 0)) + int(stacks)))
    nxt["status"] = cur
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in LAWS:
        raise StatusLawError(name)
    cap, decay, stat = LAWS[name]
    nxt = dict(state)
    cur = dict(nxt.get("status") or {})
    stacks = int(cur.get(name, 0))
    if stacks <= 0:
        nxt["status"] = cur
        nxt["stored_prose"] = 0
        return nxt
    stacks = max(0, min(cap, stacks + decay))
    cur[name] = stacks
    nxt["status"] = cur
    nxt[stat] = max(0, int(nxt.get(stat, 0)) + (decay if stacks else 0))
    nxt["stored_prose"] = 0
    return nxt


def tick_named(state: dict[str, Any]) -> dict[str, Any]:
    nxt = dict(state)
    for name in list(nxt.get("status") or {}):
        if name in LAWS:
            nxt = tick(nxt, name)
    nxt["stored_prose"] = 0
    return nxt


def known() -> tuple[str, ...]:
    return tuple(LAWS) if LAWS else STATUS
