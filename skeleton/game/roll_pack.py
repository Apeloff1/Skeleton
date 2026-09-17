"""Named rolls."""

from __future__ import annotations

from typing import Any


class RollPackError(ValueError):
    pass


ROLL = tuple(f"rl_{i:02d}" for i in range(12))


def enter(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in ROLL:
        raise RollPackError(name)
    nxt = dict(state)
    have = list(nxt.get("roll") or [])
    have.append(name)
    nxt["roll"] = have
    nxt["stored_prose"] = 0
    return nxt
