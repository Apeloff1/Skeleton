"""Named slag heaps."""

from __future__ import annotations

from typing import Any


class SlagPackError(ValueError):
    pass


SLAG = tuple(f"sg_{i:02d}" for i in range(16))


def dump(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SLAG:
        raise SlagPackError(name)
    nxt = dict(node)
    nxt["slag"] = int(nxt.get("slag", 0)) + 1 + (SLAG.index(name) % 3)
    nxt["stored_prose"] = 0
    return nxt
