"""Named cribs."""

from __future__ import annotations

from typing import Any


class CribPackError(ValueError):
    pass


CRIB = tuple(f"cb_{i:02d}" for i in range(8))


def set_crib(node: dict[str, Any], name: str) -> dict[str, Any]:
    if name not in CRIB:
        raise CribPackError(name)
    nxt = dict(node)
    nxt["crib"] = name
    nxt["stored_prose"] = 0
    return nxt
