"""Named shrouds."""

from __future__ import annotations

from typing import Any


class ShroudPackError(ValueError):
    pass


SHROUD = tuple(f"sh_{i:02d}" for i in range(12))


def set_shroud(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in SHROUD:
        raise ShroudPackError(name)
    nxt = dict(node)
    nxt["shroud"] = name
    nxt["stored_prose"] = 0
    return nxt
