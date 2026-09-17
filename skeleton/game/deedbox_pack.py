"""Named deed boxes."""

from __future__ import annotations

from typing import Any


class DeedboxPackError(ValueError):
    pass


BOX = tuple(f"dx_{i:02d}" for i in range(8))


def set_box(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in BOX:
        raise DeedboxPackError(name)
    nxt = dict(node)
    nxt["deedbox"] = name
    nxt["stored_prose"] = 0
    return nxt
