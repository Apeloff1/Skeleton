"""Named thatch lots."""

from __future__ import annotations

from typing import Any


class ThatchPackError(ValueError):
    pass


THATCH = tuple(f"th_{i:02d}" for i in range(16))


def lay(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in THATCH:
        raise ThatchPackError(name)
    nxt = dict(node)
    have = list(nxt.get("thatch") or [])
    have.append(name)
    nxt["thatch"] = have
    nxt["stored_prose"] = 0
    return nxt
