"""Named corridor passes."""

from __future__ import annotations

from typing import Any


class PassPackError(ValueError):
    pass


PASSES = tuple(f"ps_{i:02d}" for i in range(20))


def grant(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in PASSES:
        raise PassPackError(name)
    nxt = dict(state)
    have = list(nxt.get("pass") or [])
    if name not in have:
        have.append(name)
    nxt["pass"] = have
    nxt["stored_prose"] = 0
    return nxt
