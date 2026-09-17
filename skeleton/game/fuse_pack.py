"""Named fuse timers."""

from __future__ import annotations

from typing import Any


class FusePackError(ValueError):
    pass


FUSE = tuple(f"fu_{i:02d}" for i in range(16))


def lit(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FUSE:
        raise FusePackError(name)
    nxt = dict(state)
    nxt["fuse"] = name
    nxt["ticks"] = 2 + (FUSE.index(name) % 5)
    nxt["stored_prose"] = 0
    return nxt


def tick(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in FUSE:
        raise FusePackError(name)
    nxt = dict(state)
    if nxt.get("fuse") != name:
        return nxt
    nxt["ticks"] = max(0, int(nxt.get("ticks", 0)) - 1)
    if nxt["ticks"] == 0:
        nxt["heat"] = min(16, int(nxt.get("heat", 0)) + 4)
        nxt["fuse"] = ""
    nxt["stored_prose"] = 0
    return nxt
