"""Named mills."""

from __future__ import annotations

from typing import Any


class MillPackError(ValueError):
    pass


MILL = tuple(f"ml_{i:02d}" for i in range(12))


def set_mill(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in MILL:
        raise MillPackError(name)
    nxt = dict(node)
    nxt["mill"] = name
    nxt["stored_prose"] = 0
    return nxt
