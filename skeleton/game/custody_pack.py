"""Named custody holds."""

from __future__ import annotations

from typing import Any


class CustodyPackError(ValueError):
    pass


HOLD = tuple(f"cu_{i:02d}" for i in range(16))


def hold(state: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in HOLD:
        raise CustodyPackError(name)
    nxt = dict(state)
    cur = dict(nxt.get("custody") or {})
    cur[name] = who
    nxt["custody"] = cur
    nxt["stored_prose"] = 0
    return nxt
