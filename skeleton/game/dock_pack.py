"""Named docks."""

from __future__ import annotations

from typing import Any


class DockPackError(ValueError):
    pass


DOCK = tuple(f"dk_{i:02d}" for i in range(16))


def berth(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in DOCK:
        raise DockPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("dock") or {})
    cur[name] = who
    nxt["dock"] = cur
    nxt["stored_prose"] = 0
    return nxt
