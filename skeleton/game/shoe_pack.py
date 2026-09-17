"""Named mill shoes."""

from __future__ import annotations

from typing import Any


class ShoePackError(ValueError):
    pass


SHOE = tuple(f"sh_{i:02d}" for i in range(8))


def set_shoe(node: dict[str, Any], name: str, open_: int) -> dict[str, Any]:
    if name not in SHOE:
        raise ShoePackError(name)
    nxt = dict(node)
    nxt["shoe"] = name
    nxt["feed"] = max(0, int(open_))
    nxt["stored_prose"] = 0
    return nxt
