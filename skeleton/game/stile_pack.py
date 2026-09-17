"""Named stiles."""

from __future__ import annotations

from typing import Any


class StilePackError(ValueError):
    pass


STILE = tuple(f"st_{i:02d}" for i in range(8))


def set_stile(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in STILE:
        raise StilePackError(name)
    nxt = dict(node)
    nxt["stile"] = name
    nxt["stored_prose"] = 0
    return nxt
