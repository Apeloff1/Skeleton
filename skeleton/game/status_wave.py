"""Wave-4 extra statuses."""

from __future__ import annotations

from typing import Any


class StatusWaveError(ValueError):
    pass


STATUS = (
    "frost", "scald", "sting", "numb", "glowburn", "soot", "oil", "static",
    "pulse", "throb", "ache", "itch", "haze", "blur", "ring", "whine",
    "clench", "slack", "brittle", "tacky", "slick", "grit", "film", "crust",
    "rift", "seam", "knot", "fray",
)


def apply(state: dict[str, Any], name: str, n: int = 1) -> dict[str, Any]:
    if name not in STATUS:
        raise StatusWaveError(name)
    cap = 4 + (STATUS.index(name) % 8)
    nxt = dict(state)
    cur = dict(nxt.get("status") or {})
    cur[name] = min(cap, max(0, int(cur.get(name, 0)) + n))
    nxt["status"] = cur
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STATUS:
        raise StatusWaveError(name)
    i = STATUS.index(name)
    decay = -1 if i % 4 else -2
    stat = ("heat", "hp", "alert", "sleep", "xp")[i % 5]
    nxt = dict(state)
    cur = dict(nxt.get("status") or {})
    v = max(0, int(cur.get(name, 0)) + decay)
    cur[name] = v
    nxt["status"] = cur
    nxt[stat] = max(0, int(nxt.get(stat, 0)) + (v and decay))
    nxt["stored_prose"] = 0
    return nxt
