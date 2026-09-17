"""Named shuttles."""

from __future__ import annotations

from typing import Any


class ShuttlePackError(ValueError):
    pass


SHUTTLE = tuple(f"sh_{i:02d}" for i in range(12))


def throw(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHUTTLE:
        raise ShuttlePackError(name)
    nxt = dict(state)
    nxt["shuttle"] = name
    nxt["picks"] = int(nxt.get("picks", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
