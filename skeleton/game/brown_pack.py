"""Named brown coats."""

from __future__ import annotations

from typing import Any


class BrownPackError(ValueError):
    pass


BROWN = tuple(f"br_{i:02d}" for i in range(12))


def lay(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BROWN:
        raise BrownPackError(name)
    nxt = dict(node)
    nxt["brown"] = name
    nxt["coat"] = int(nxt.get("coat", 0)) + 1
    nxt["stored_prose"] = 0
    return nxt
