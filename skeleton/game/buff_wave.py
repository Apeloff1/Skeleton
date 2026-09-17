"""Named buffs."""

from __future__ import annotations

from typing import Any


class BuffWaveError(ValueError):
    pass


BUFFS = tuple(f"buf_{i:02d}" for i in range(24))


def on(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BUFFS:
        raise BuffWaveError(name)
    nxt = dict(state)
    cur = dict(nxt.get("buff") or {})
    cur[name] = min(8, int(cur.get(name, 0)) + 1)
    nxt["buff"] = cur
    nxt["stored_prose"] = 0
    return nxt


def off(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BUFFS:
        raise BuffWaveError(name)
    nxt = dict(state)
    cur = dict(nxt.get("buff") or {})
    cur.pop(name, None)
    nxt["buff"] = cur
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BUFFS:
        raise BuffWaveError(name)
    nxt = dict(state)
    cur = dict(nxt.get("buff") or {})
    v = max(0, int(cur.get(name, 0)) - 1)
    if v:
        cur[name] = v
    else:
        cur.pop(name, None)
    nxt["buff"] = cur
    nxt["heat"] = max(0, int(nxt.get("heat", 0)) + (((BUFFS.index(name) % 3) - 1) if v else 0))
    nxt["stored_prose"] = 0
    return nxt
