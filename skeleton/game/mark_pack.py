"""Named memory marks."""

from __future__ import annotations

from typing import Any


class MarkPackError(ValueError):
    pass


MARKS = tuple(f"mk_{i:02d}" for i in range(24))


def set_mark(state: dict[str, Any], name: str, room: str) -> dict[str, Any]:
    if name not in MARKS:
        raise MarkPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("marks") or {})
    cur[name] = room
    nxt["marks"] = cur
    nxt["stored_prose"] = 0
    return nxt
