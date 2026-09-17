"""Named schedule slots."""

from __future__ import annotations

from typing import Any


class SchedPackError(ValueError):
    pass


SLOTS = tuple(f"sd_{i:02d}" for i in range(24))


def book(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in SLOTS:
        raise SchedPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("sched") or {})
    cur[name] = who
    nxt["sched"] = cur
    nxt["stored_prose"] = 0
    return nxt
