"""Named holds."""

from __future__ import annotations

from typing import Any


class HoldPackError(ValueError):
    pass


HOLD = tuple(f"hd_{i:02d}" for i in range(24))


def set_hold(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in HOLD:
        raise HoldPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("hold") or {})
    cur[name] = who
    nxt["hold"] = cur
    nxt["stored_prose"] = 0
    return nxt
