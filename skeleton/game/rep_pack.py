"""Named reputation tracks."""

from __future__ import annotations

from typing import Any


class RepPackError(ValueError):
    pass


REPS = tuple(f"rp_{i:02d}" for i in range(20))


def add(state: dict[str, Any], name: str, d: int) -> dict[str, Any]:
    if name not in REPS:
        raise RepPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("rep") or {})
    cur[name] = max(-16, min(16, int(cur.get(name, 0)) + int(d)))
    nxt["rep"] = cur
    nxt["stored_prose"] = 0
    return nxt
