"""Named watch shifts."""

from __future__ import annotations

from typing import Any


class WatchPackError(ValueError):
    pass


WATCH = tuple(f"wt_{i:02d}" for i in range(20))


def post(state: dict[str, Any], name: str, room: str) -> dict[str, Any]:
    if name not in WATCH:
        raise WatchPackError(name)
    nxt = dict(state)
    nxt["watch"] = name
    nxt["room"] = room
    nxt["alert"] = int(nxt.get("alert", 0)) + (WATCH.index(name) % 2)
    nxt["stored_prose"] = 0
    return nxt
