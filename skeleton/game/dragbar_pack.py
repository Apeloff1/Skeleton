"""Named drag bars."""

from __future__ import annotations

from typing import Any


class DragbarPackError(ValueError):
    pass


BAR = tuple(f"db_{i:02d}" for i in range(8))


def drag(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BAR:
        raise DragbarPackError(name)
    nxt = dict(state)
    nxt["dragbar"] = name
    nxt["pass"] = int(nxt.get("pass", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
