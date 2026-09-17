"""More named status laws."""

from __future__ import annotations

from typing import Any


class StatusLaw2Error(ValueError):
    pass


LAWS: dict[str, tuple[int, int, str]] = {
    "spark": (6, -1, "coil"), "rust": (8, -1, "parts"), "dust": (6, -1, "scrap"),
    "echo": (8, -1, "alert"), "hum": (6, -1, "heat"), "drip": (5, -1, "hp"),
    "glow": (4, -1, "heat"), "shade": (9, -1, "los"), "grip": (4, -1, "key"),
    "slip": (6, -1, "alert"), "thrum": (10, -1, "heat"), "hush": (8, -1, "alert"),
    "gnaw": (7, -1, "hp"), "bloom": (5, -1, "xp"), "wilt": (6, -1, "sleep"),
    "surge": (12, -2, "heat"), "ebb": (4, -1, "heat"), "bind": (3, 0, "locked"),
    "loose": (3, 0, "locked"), "marking": (10, -1, "alert"),
}


def apply(state: dict[str, Any], name: str, stacks: int = 1) -> dict[str, Any]:
    if name not in LAWS:
        raise StatusLaw2Error(name)
    cap, _decay, _stat = LAWS[name]
    nxt = dict(state)
    cur = dict(nxt.get("status") or {})
    cur[name] = min(cap, max(0, int(cur.get(name, 0)) + int(stacks)))
    nxt["status"] = cur
    nxt["stored_prose"] = 0
    return nxt


def tick_named(state: dict[str, Any]) -> dict[str, Any]:
    nxt = dict(state)
    cur = dict(nxt.get("status") or {})
    for name, (cap, decay, stat) in LAWS.items():
        stacks = int(cur.get(name, 0))
        if stacks <= 0:
            continue
        stacks = max(0, min(cap, stacks + decay))
        cur[name] = stacks
        nxt[stat] = max(0, int(nxt.get(stat, 0)) + (decay if stacks else 0))
    nxt["status"] = cur
    nxt["stored_prose"] = 0
    return nxt
