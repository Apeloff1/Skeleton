"""Named twists."""

from __future__ import annotations

from typing import Any


class TwistPackError(ValueError):
    pass


TWIST = tuple(f"tw_{i:02d}" for i in range(12))


def lay(state: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in TWIST:
        raise TwistPackError(name)
    nxt = dict(state)
    nxt["twist"] = name
    nxt["lay"] = int(nxt.get("lay", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
