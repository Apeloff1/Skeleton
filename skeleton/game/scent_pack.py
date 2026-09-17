"""Named scent trails."""

from __future__ import annotations

from typing import Any


class ScentPackError(ValueError):
    pass


SCENT = tuple(f"sc_{i:02d}" for i in range(24))


def lay(node: dict[str, Any], name: str, who: str) -> dict[str, Any]:
    if name not in SCENT:
        raise ScentPackError(name)
    nxt = dict(node)
    nxt["scent"] = name
    nxt["who"] = who
    nxt["age"] = SCENT.index(name) % 4
    nxt["stored_prose"] = 0
    return nxt
