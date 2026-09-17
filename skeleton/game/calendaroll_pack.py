"""Named calendar rolls."""

from __future__ import annotations

from typing import Any


class CalendarollPackError(ValueError):
    pass


CAL = tuple(f"cr_{i:02d}" for i in range(12))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CAL:
        raise CalendarollPackError(name)
    nxt = dict(state)
    nxt["calendaroll"] = name
    nxt["entered"] = 1
    nxt["stored_prose"] = 0
    return nxt
