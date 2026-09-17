"""Named lantern oils."""

from __future__ import annotations

from typing import Any


class OilPackError(ValueError):
    pass


OIL = tuple(f"ol_{i:02d}" for i in range(16))


def burn(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in OIL:
        raise OilPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("oil") or {})
    if int(cur.get(name, 0)) < 1:
        raise OilPackError("empty")
    cur[name] = int(cur.get(name, 0)) - 1
    nxt["oil"] = cur
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 1)
    nxt["stored_prose"] = 0
    return nxt


def fill(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in OIL:
        raise OilPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("oil") or {})
    cur[name] = int(cur.get(name, 0)) + 1
    nxt["oil"] = cur
    nxt["stored_prose"] = 0
    return nxt
